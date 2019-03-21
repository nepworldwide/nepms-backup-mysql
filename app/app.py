#!/usr/bin/env python
import sys
import os
import logging as log
import argparse
import datetime as dt
import time
from subprocess import CalledProcessError, check_output, STDOUT
import json
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
from boto3.s3.transfer import S3Transfer
import boto3


# Helper function to get the script dir
def get_script_path(some_file=None):
    script_directory = os.path.dirname(os.path.realpath(sys.argv[0]))
    if some_file is None:
        # Return just app dir
        return script_directory
    else:
        # Return full file path to specified file, as if it was in app dir
        return os.path.join(script_directory, some_file)


# Set logging level to debug
log.basicConfig(level=log.INFO, format='%(asctime)s.%(msecs)03d %(levelname)s %(message)s')

# Parse arguments
parser = argparse.ArgumentParser(description='Backup MongoDB databases')
parser.add_argument('-c', '--conf-file',
                    type=str,
                    required=False,
                    default=get_script_path('conf.json'),
                    help='default conf.json')
parser.add_argument('-l', '--log-level',
                    type=str,
                    required=False,
                    default='info',
                    help='Log level (default: info [critical, error, warning, info, debug])')


# Switches the logging level, depending on the input
def log_level_switch(log_level):
    return {
        'critical': log.CRITICAL,
        'error': log.ERROR,
        'warning': log.WARNING,
        'info': log.INFO,
        'debug': log.DEBUG,
    }[log_level]


# Read JSON file and returns the loaded dict
def get_json_conf(json_file):
    try:
        log.info(f'Reading conf file "{json_file}"')
        with open(json_file, 'r') as f:
            conf = json.load(f)
    except Exception as e:
        log.error(f'Could not read the file: {e}')
        sys.exit(1)

    log.debug(f'Read conf "{json.dumps(conf)}"')
    return conf


# Actual backup
# With mysqldump binary
def run_job(conf):

    name = conf['name']
    output_dir = conf['out']
    util = conf['util']
    host = conf['host']
    db = conf['db']
    db_user = conf['user']
    db_pass = conf['password']
    dump_type = conf['type']

    compression = conf['compression']
    if 'included' in conf:
        tables_included = conf['included']
    if 'excluded' in conf:
        tables_excluded = conf['excluded']

    # TODO add inclusion and exclusion
    filename = f"{name}.sql"
    output = f"{output_dir}/{filename}"
    schema_only_flags = '--no-data -R -E' if dump_type == 'schema' else ''

    create_dir_cmd = f"mkdir -p {output_dir}"
    if db_pass != '':
        db_dump_cmd = f"{util} -h {host} -u {db_user} -p{db_pass} {schema_only_flags} --single-transaction  {db} > {output}"
    else:
        db_dump_cmd = f"{util} -h {host} -u {db_user} {schema_only_flags} --single-transaction {db} > {output}"

    job_start_time = time.time()
    try:
        # Create dir
        log.info(f"Running dump for job: {conf['name']}")
        check_output(create_dir_cmd, stderr=STDOUT, shell=True)
        # Dump
        dump_start_time = time.time()
        log.info(f"Creating dump file: '{output}'")
        check_output(db_dump_cmd, stderr=STDOUT, shell=True)
        dump_size = os.stat(output).st_size
        dump_duration = round((time.time() - dump_start_time)*1000)
        log.info(f"Finished creating dump file. "
                 f"Size: {dump_size} bytes. "
                 f"Duration: {dump_duration} ms")

        compressed_size = None
        compression_duration = None
        # Compression
        if compression:
            compression_cmd = f"gzip {output}"
            compression_start_time = time.time()
            log.info(f"Compressing file: '{output}'")
            check_output(compression_cmd, stderr=STDOUT, shell=True)
            compressed_size = os.stat(f"{output}.gz").st_size
            compression_duration = round((time.time() - compression_start_time)*1000)
            log.info(f"Finished compressing file. "
                     f"Size: {compressed_size} bytes. "
                     f"Duration: {compression_duration} ms")

        job_stats = dict(
            duration=round((time.time() - job_start_time)*1000),
            duration_dump=dump_duration,
            duration_compression=compression_duration,
            size_dump=dump_size,
            size_compressed=compressed_size
        )
        return job_stats
    except CalledProcessError as e:
        log.error(f"Backup job has failed after {round((time.time() - job_start_time)*1000)} ms. "
                  f"Error: {e.output}")
        raise RuntimeError(f"Quitting due to previous errors")


# Push registry to prometheus
def push_to_prometheus(prometheus_host, prometheus_job, registry):
    try:
        log.info(f'Sending data to Prometheus host: "{prometheus_host}", job: "{prometheus_job}"')
        start_time = time.time()
        push_to_gateway(prometheus_host, job=prometheus_job, registry=registry)
        duration = time.time() - start_time
        log.info(f"Successfully sent data to Prometheus. Time taken: {duration} seconds")
    except Exception as e:
        raise Exception(f"Failed to send data to Prometheus: {e}")


# Upload to AWS s3
def upload_to_aws(conf, backup):

    global db_backup_status
    global db_backup_runtime

    try:
        start_time = time.time()

        access_key = conf['access_key']
        secret_key = conf['secret_key']
        folder_name = conf['path']
        bucket_name = conf['bucket']
        s3_filename = folder_name + os.path.basename(backup)

        log.info(f'Uploading to s3. Bucket: "{bucket_name}", Source: "{backup}", Destination: "{s3_filename}"')

        client = boto3.client('s3', aws_access_key_id=access_key, aws_secret_access_key=secret_key)
        transfer = S3Transfer(client)
        transfer.upload_file(backup, bucket_name, s3_filename)

        duration = round(time.time() - start_time)

        log.info(f"Successfully uploaded to s3. Time taken: {duration} seconds")

        db_backup_runtime.labels('upload').set(duration)
        db_backup_status.labels('upload').set(1)
    except Exception as e:
        duration = round(time.time() - start_time)
        db_backup_runtime.labels('upload').set(duration)
        db_backup_status.labels('upload').set(0)
        raise Exception(f"Upload to s3 has failed: {e}")


# App
if __name__ == '__main__':

    args = parser.parse_args()
    log.debug(f'App args "{args}"')

    conf = get_json_conf(args.conf_file)
    log.basicConfig(level=log_level_switch(args.log_level))

    backup_db_conf = conf['database']
    backup_conf = conf['backup']
    backup_jobs = backup_conf['dumps']

    out = backup_conf['output_dir']
    assert os.path.isdir(out), f"Directory {out} can't be found."

    ts = dt.datetime.now()
    out = os.path.abspath(os.path.join(out, f"{ts.strftime('%Y-%m-%d_%H%M%S')}"))

    for job in backup_jobs:
        if job['enabled']:
            job_conf = dict(
                host=backup_db_conf['host'],
                db=backup_db_conf['db'],
                user=backup_db_conf['user'],
                password=backup_db_conf['password'],
                util=backup_conf['mysqldump'],
                output_dir=out,
                name=job['name'],
                out=out,
                type=job['type'],
                compression=job['compression'],
                excluded=job['excluded'] if 'excluded' in job else [],
                included=job['included'] if 'included' in job else []
            )
            log.debug(f"Job params: {job_conf}")
            # Run backup job
            try:
                job_stats = run_job(job_conf)
            except AssertionError as msg:
                log.error(msg)

    # TODO add aws upload
    # TODO add prometheus metrics push

    """
    aws_enabled = conf['aws']['enabled']

    prometheus_enabled = conf['prometheus']['enabled']
    prometheus_host = conf['prometheus']['host']
    prometheus_job = conf['prometheus']['job']

    
    metric_status_label = conf['prometheus']['labels'][0]['label']
    metric_status_label_name = conf['prometheus']['labels'][0]['label_name']

    metric_runtime_label = conf['prometheus']['labels'][1]['label']
    metric_runtime_label_name = conf['prometheus']['labels'][1]['label_name']

    # Prometheus init
    registry = CollectorRegistry()
    db_backup_status = Gauge(metric_status_label, metric_status_label_name, ['action'], registry=registry)
    db_backup_runtime = Gauge(metric_runtime_label, metric_runtime_label_name, ['action'], registry=registry)

    if aws_enabled:
        upload_to_aws(conf['aws'], local_backup)

        try:
            log.info(f'Removing local backup "{local_backup}"')
            os.remove(local_backup)
            log.info('Removal of local backup has been successful')
        except Exception as e:
            log.info(f'Removal of local backup has failed: "{e}"')
    else:
        log.info('Backup upload is disabled')

    try:
        if prometheus_enabled:
            log.info('Prometheus is enabled')
            push_to_prometheus(prometheus_host, prometheus_job, registry)
        else:
            log.info('Prometheus is disabled, data will not be sent to prometheus')
    except Exception as e:
        log.info(f'Sending data to Prometheus has failed: "{e}"')
    """
