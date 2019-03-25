# nepms-backup-mysql
_Works with both MySQL and MariaDB_ (see compatibility below)

MySQL dump that creates full backup for configured database, different scenarios can be configured.
- Highly configurable
  - Specify mysqldump binary to be used
  - File output location
  - Dump data or Schema config templates
  - Include or exclude tables per database
- Can Make use of `~/.my.cnf`
- Optional retention period (by count of old backups)
- Optional compression with gzip
- Optional upload to AWS S3
- Optional metrics push to prometheus pushgateway
## Configuration
### Example configuration
`app/conf.sample.json`
#### Use case
- Create backup of Zabbix DB with following scenarios (jobs):
   - Schema
      - All tables
      - Backup Enabled
      - Compression disabled
   - Config data
      - Exclude some heavy metric data and other non-essential tables
      - Backup Enabled
      - Compression enabled
   - Metric data
      - Include some heavy metric data bearing tables
      - Backup Disabled
- Use custom mysqldump binary
- Rely on `~/.my.cnf` for DB connection password
- Keep last 3 backups locally
- Prometheus metric push enabled
- AWS upload enabled
### Configuration docs
Configuration is in JSON and the script expects it to be in the same directory with name `conf.json`.
#### database (mandatory)
_Any unspecified setting, will be taken from default `my.cnf` file locations_
 
__`host`__ Optional. DNS/IP of the database connection. Example: `localhost`.

__`db`__ Optional. Name of the database connection.

__`user`__ Optional. User of the database connection.

__`password`__ Optional. User of the database connection.
#### prometheus (optional)
More info: https://github.com/prometheus/pushgateway.

_All below keys are mandatory_

__`enabled`__   JSON Boolean type. The `prometheus` key dict can be configured, but disabled this way.

__`host`__  DNS/IP of the prometheus pushgateway. Example: `prometheus-pushgateway.pvc.com`.

__`job`__   Job title for prometheus pushgateway. Used in registry creation.
#### aws
_All below keys are mandatory_

__`enabled`__   JSON Boolean type. The `prometheus` key dict can be configured, but disabled this way.

__`bucket`__    AWS bucket name.

__`path`__    AWS path in bucket.

__`access_key`__    AWS access token.

__`secret_key`__    AWS secret key.
#### backup
__`mysqldump_bin`__ Optional. `mysqldump` binary full file path. Defaults to mysqldump available in `$PATH`.

__`output_dir`__ Mandatory. Specify the output directory. Each run will have its own timestamped directory within.

__`keep_local_backups`__ Retention of how many latest backups to keep (including current)

__`jobs`__ Mandatory. JSON array of dicts. These dicts describe a backup job. See example.

__`jobs.name`__ Mandatory. Name for the backup job. This will later be used in prometheus push, if enabled.

__`jobs.type`__ Mandatory. See for more info below.

__`jobs.enabled`__ Mandatory. JSON Boolean type. Job can be configured, but disabled this way.

__`jobs.compression`__ Mandatory. JSON Boolean type. The dump for this job can be either enabled or disabled.

__`jobs.include`__ JSON Array of string values that represent the table names to be included in the backup. Only these tables will be backed up!

__`jobs.exclude`__ JSON Array of string values that represent the table names to be excluded from the backup. These tables will NOT be backed up!
### jobs.type
This setting will tell mysqldump what kind of backup we want.
Currently predefined and allowed string values are `schema` or `data`.
#### schema
Will use following mysqldump options: ```--no-data --triggers --routines --events```
#### data
Will use following mysqldump options: ```--no-create-info --skip-triggers```
## Logging
One can choose to enable different levels of log with optional `-l|--log-level <level>`.

Default is going to is `info` level, which will log everything that is "info" and more severe. i.e. warnings, errors etc
Available levels
- debug
- info
- warning
- error
- critical

Sample log with debug level
```
*/nepms-backup-mysql/venv/bin/python */nepms-backup-mysql/app/app.py --log-level debug
2019-03-25 15:51:22,296.296 INFO Reading conf file "*/nepms-backup-mysql/app/conf.json"
2019-03-25 15:51:22,297.297 INFO Running dump for job: db_schema
2019-03-25 15:51:22,297.297 INFO Creating dump directory: /data/db/backups/2019-03-25_155122
2019-03-25 15:51:22,301.301 INFO Creating dump file: '/data/db/backups/2019-03-25_155122/db_schema.sql'
2019-03-25 15:51:24,654.654 INFO Finished creating dump file. Size: 154988 bytes. Duration: 2353 ms
2019-03-25 15:51:24,654.654 INFO Compressing file: '/data/db/backups/2019-03-25_155122/db_schema.sql'
2019-03-25 15:51:24,667.667 INFO Finished compressing file. Size: 15418 bytes. Duration: 13 ms
2019-03-25 15:51:24,667.667 INFO Job has 'exclude' tables
2019-03-25 15:51:24,667.667 INFO Running dump for job: db_config
2019-03-25 15:51:24,667.667 INFO Creating dump directory: /data/db/backups/2019-03-25_155122
2019-03-25 15:51:24,672.672 INFO Creating dump file: '/data/db/backups/2019-03-25_155122/db_config.sql'
2019-03-25 15:51:47,364.364 INFO Finished creating dump file. Size: 244031995 bytes. Duration: 22692 ms
2019-03-25 15:51:47,365.365 INFO Compressing file: '/data/db/backups/2019-03-25_155122/db_config.sql'
2019-03-25 15:51:53,162.162 INFO Finished compressing file. Size: 59153792 bytes. Duration: 5797 ms
2019-03-25 15:51:53,162.162 INFO Running AWS upload for '/data/db/backups/2019-03-25_155122'
2019-03-25 15:51:53,227.227 INFO Uploading to s3. Bucket: "backup", Source: "/data/db/backups/2019-03-25_155122/db_config.sql.gz", Destination: "zabbix-db/2019-03-25_155122/db_config.sql.gz"
2019-03-25 15:51:59,819.819 INFO Uploading to s3. Bucket: "backup", Source: "/data/db/backups/2019-03-25_155122/db_schema.sql.gz", Destination: "zabbix-db/2019-03-25_155122/db_schema.sql.gz"
2019-03-25 15:51:59,915.915 INFO Successfully uploaded to s3. Time taken: 6753 ms
2019-03-25 15:51:59,915.915 INFO Retention is enabled, checking for old dirs
2019-03-25 15:51:59,916.916 INFO Backup directory has 2 dirs. Starting cleanup.
2019-03-25 15:51:59,916.916 INFO Following directories will be removed: ['/data/db/backups/2019-03-25_155122', '/data/db/backups/2019-03-25_154610']
2019-03-25 15:51:59,920.920 INFO Following directory has been removed: '/data/db/backups/2019-03-25_155122'
2019-03-25 15:51:59,921.921 INFO Following directory has been removed: '/data/db/backups/2019-03-25_154610'
2019-03-25 15:51:59,921.921 INFO Prometheus is enabled
2019-03-25 15:51:59,921.921 INFO Sending stats to prometheus gateway
2019-03-25 15:51:59,921.921 INFO Sending data to Prometheus host: "prometheus-pushgateway.vpc2.mnw.no", job: "zabbix_db_backup"
2019-03-25 15:51:59,929.929 INFO Successfully sent data to Prometheus. Time taken: 0.008221864700317383 seconds

Process finished with exit code 0
```

## Compatibility
Tested with MariaDB 5.5

Never version should work, but there is no guarantee at the moment.
## TODO
- Add option to specify string of options to be used with mysqldump binary
- Test with newer releases

## Development
Pretty straight forward.
- Clone the repo
- ???
- Profit

This repo also includes pre-commit config in `.pre-commit-config.yaml`. If you know what it is and how to use it,
then you will also find useful `requirements-dev.txt`, which includes the packages you need to run pre-commit config included.

## License
MIT

Happy dumping!