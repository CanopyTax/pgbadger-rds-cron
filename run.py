#!/usr/bin/python3

import schedule
import time
import os
import subprocess
import psutil
import boto3

from datetime import datetime
from operator import itemgetter


rds = boto3.client('rds')


def raiser(e):
    raise e


def download_log_files(db_name):
    rds = boto3.client('rds')
    files = rds.describe_db_log_files(DBInstanceIdentifier=db_name)

    # Sort based on touched time - ignore postgres.log
    files = files.get('DescribeDBLogFiles')
    files = [n.get('LogFileName') for n in
             sorted(files, key=itemgetter('LastWritten'), reverse=True)
             if n.get('LogFileName') != 'error/postgres.log']

    # Get a weeks worth of files
    files = files[:7]

    # Download
    for name in files:
        print('Downloading {} ...'.format(name))
        download_log(name, db_name)

    print('Downloads complete')

    return files


def download_log(log_name, db_name, marker='0'):
    result = rds.download_db_log_file_portion(
        DBInstanceIdentifier=db_name,
        Marker=marker,
        LogFileName=log_name
    )
    mode = 'ab'
    if marker == '0':
        mode = 'wb'
    with open('logs/' + log_name, mode) as f:
        f.write(result.get('LogFileData').encode())
    if result.get('AdditionalDataPending'):
        download_log(log_name, db_name, marker=result.get('Marker'))


def run_pgbadger(file_list):
    file_list = ['logs/' + f for f in file_list]
    subprocess.check_call([
        './pgbadger',
        '-j', str(psutil.cpu_count()),
        '-p', '%t:%r:%u@%d:[%p]:'
        ] + file_list
    )


def upload_to_s3(bucket, key):
    s3 = boto3.resource('s3')
    s3.Object(bucket, key).put(
        Body=open('out.html', 'rb'),
        ContentType='html',
        ACL='public-read'
        )


def run():
    db_name = os.getenv('DB_NAME') or \
              raiser(ValueError('DB_NAME is required'))
    bucket = os.getenv('S3_BUCKET') or \
             raiser(ValueError('S3_BUCKET is required'))
    key = os.getenv('S3_KEY', 'pgbadger.html')
    try:
        files = download_log_files(db_name)
        run_pgbadger(files)
        upload_to_s3(bucket, key)
    except Exception as e:
        raise


def build_schedule():
    print('Starting sqlcron. Current time: {}'
          .format(str(datetime.now())))
    interval = int(os.getenv('INTERVAL', '1'))
    unit = os.getenv('UNIT', 'day')
    time_of_day = os.getenv('TIME')

    evaluation_string = 'schedule.every(interval).' + unit
    if time_of_day:
        evaluation_string += '.at(time_of_day)'

    evaluation_string += '.do(run)'
    eval(evaluation_string)


def run_schedule():
    while True:
        sleep_time = schedule.next_run() - datetime.now()
        print('Next job to run at {}, which is {} from now'
              .format(str(schedule.next_run()), str(sleep_time)))

        # Sleep an extra second to make up for microseconds
        time.sleep(max(1, sleep_time.seconds + 1))
        schedule.run_pending()


if __name__ == "__main__":
    if not os.getenv('INTERVAL') and \
            not os.getenv('UNIT') and \
            not os.getenv('TIME'):
        run()
    elif 'now' == os.getenv('UNIT', 'none').lower():
        # Run now and exit instead of using a cron
        run()
    else:
        build_schedule()
        run_schedule()
