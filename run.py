#!/usr/bin/python3
import traceback

import schedule
import time
import os
import subprocess
import psutil
import boto3
import pickle

from datetime import datetime
from operator import itemgetter


rds = boto3.client('rds', region_name=os.getenv('REGION', 'us-west-2'))

log_state = dict()


def raiser(e):
    raise e


def download_log_files(db_name):
    files = rds.describe_db_log_files(DBInstanceIdentifier=db_name)

    # Sort based on touched time - ignore postgres.log
    files = files.get('DescribeDBLogFiles')
    files = [n.get('LogFileName') for n in
             sorted(files, key=itemgetter('LastWritten'), reverse=True)
             if n.get('LogFileName') != 'error/postgres.log']

    # Get a weeks worth of files
    files = files[:3]

    # Download
    for name in files:
        print('Downloading {} ...'.format(name))
        download_log(name, db_name)

    print('Downloads complete')
    # Delete old files
    for d in os.listdir('logs/'):
        if os.path.isdir('./logs/' + d):
            for f in os.listdir('logs/' + d):
                if d + '/' + f not in files:
                    os.remove('logs/' + d + '/' + f)
        if os.path.isfile('logs/' + d):
            if d not in files:
                os.remove('logs/' + d)

    return files


def download_log(log_name, db_name):
    marker = log_state.get(log_name, '0')
    mode = 'ab'
    if marker == '0':
        mode = 'wb'
    with open('logs/' + log_name, mode) as f:
        try:
            while True:
                result = rds.download_db_log_file_portion(
                    DBInstanceIdentifier=db_name,
                    Marker=marker,
                    LogFileName=log_name,
                    NumberOfLines=99999999
                )
                # For debugging
                # if not result.get('AdditionalDataPending'):
                #     print('no data pending, marker:{}'
                #           .format(result.get('Marker')))
                if marker == result.get('Marker'):  # no more data
                    marker = result.get('Marker')
                    return
                f.write(result.get('LogFileData').encode())
                marker = result.get('Marker')
        finally:
            log_state[log_name] = marker


def run_pgbadger(file_list):
    file_list = ['logs/' + f for f in file_list]
    subprocess.check_call([
        './pgbadger',
        '-j', str(psutil.cpu_count()),
        '-X',
        '-I',
        '-O', os.getcwd() + '/pg_reports',
        '-p', '%t:%r:%u@%d:[%p]:'
        ] + file_list
    )


def sync_s3(bucket, key, upload=False):
    local_path = os.getcwd() + '/pg_reports'
    s3_path = 's3://' + bucket + '/' + key
    sync_path = [s3_path, local_path]
    if upload:
        sync_path = sync_path[::-1]
    subprocess.check_call([
        '/home/nhumrich/.awsenv/bin/aws',
        's3',
        'sync',
        ] + sync_path
    )


def upload_to_s3(bucket, key, region):
    s3 = boto3.resource('s3', region_name=region)
    s3.Object(bucket, key).put(
        Body=open('out.html', 'rb'),
        ContentType='html',
        ACL='public-read'
        )


def get_log_states():
    global log_state
    try:
        with open('logs/status.p', 'rb') as p:
            log_state = pickle.load(p)
    except FileNotFoundError:
        log_state = dict()


def save_log_states():
    with open('logs/status.p', 'wb') as p:
        pickle.dump(log_state, p)


def run():
    get_log_states()
    db_name = os.getenv('DB_NAME') or \
              raiser(ValueError('DB_NAME is required'))
    bucket = os.getenv('S3_BUCKET') or \
             raiser(ValueError('S3_BUCKET is required'))
    region = os.getenv('REGION', 'us-west-2')
    key = os.getenv('S3_KEY', 'pgbadger/')
    try:
        files = download_log_files(db_name)
        sync_s3(bucket, key)
        run_pgbadger(files)
        sync_s3(bucket, key, upload=True)
        # upload_to_s3(bucket, key, region)
    except Exception as e:
        traceback.print_exc()
    finally:
        save_log_states()


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
