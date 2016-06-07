# pgbadger-rds-cron

This container pulls logs from rds and parses them with pgbadger.
The resulting html file is uploaded to s3. 
The file is replaced everytime as if the page was keeping itself up-to-date.
This way, all devs can use a single link and you dont have to maintain files.
This does however add the caveat that you loose all data more than a week old.


## How do I use it

Ideally you should use instance-profiles for controlling permissions.
But if you need to use environment variables, you can use the standard AWS ones.

     docker run -t -e AWS_SECRET_ACCESS_KEY=xxx -e AWS_ACCESS_KEY_ID=xxx -e AWS_DEFAULT_REGION=xxx -e BUCKET=my-bucket -e DB_INSTANCE_IDENTIFIER=my-rds-postgres canopytax/pgbadger-rds-cron
      
## IAM Permissions
 
 Your AIM User/Instance Profile will need the following access in IAM. 
 
 ```
 {
     "Version": "2012-10-17",
     "Statement": [
         {
             "Sid": "Stmt1465312344000",
             "Effect": "Allow",
             "Action": [
                 "rds:DescribeDBLogFiles",
                 "rds:DownloadDBLogFilePortion"
             ],
             "Resource": [
                 "arn:aws:rds:{region}:{accountID}:db:{dbName}"
             ]
         },
         {
             "Sid": "s3statement",
             "Effect": "Allow",
             "Action": [
                 "s3:PutObject",
                 "s3:PutObjectAcl"
             ],
             "Resource": "arn:aws:s3:::{s3Bucket}/*"
         }
     ]
 }
 ```
 

## Setting up RDS

You have to enable logging on rds in order for pgbadger to work right.
You can enable with the CLI or using the console. You have to first be on a custon parameter group.

Here is a screenshot of the options set to make things work.

![image](/parameters.png?raw=true "RDS Parameters")

You can adjust `log_min_duration_statement` to your liking. 
If you would like to log every query, set it to 0. 
If you would instead like to log only longer queries, adjust it higher. 
The time is in milliseconds.

### CLI
 
If you want to use the CLI, you can use this command (modify for each option):

```
aws rds modify-db-parameter-group --db-parameter-group-name postgres-custom --parameters "ParameterName=log_min_duration_statement, ParameterValue=0, ApplyMethod=immediate"
```

## Running as a cron

Ideally you want this to run every X minutes, so your results stay up to date.
If you just run the container as is, it will run once. 
If you would like to run at an interval, just set the environment variables.

The environment variables needed are:

    INTERVAL: How many units (Optional, default=1)
    UNIT: Unit of time (Optional, default=day)
    TIME: Specific time of each day to run (Optional, used instead of INTERVAL and UNIT)
    
For example, if you want to update every 15 minutes, you would set `INTERVAL=5` and `UNIT=minutes`.
If you would like to run your job every day at 6:00pm (server time) you would set `TIME=18:00`.


Example:

    docker run -t  -e INTERVAL=15 -e UNIT=minutes -e BUCKET=my-bucket -e DB_INSTANCE_IDENTIFIER=my-rds-postgres canopytax/pgbadger-rds-cron
