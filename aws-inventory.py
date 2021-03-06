#!/usr/bin/env python
import signal
import sys
from time import gmtime, strftime

from tabulate import tabulate
import boto.ec2.elb
import boto.rds
import boto.vpc
import boto.elasticache
import boto3
import argparse
import logging

__version__ = "0.2"


def signal_handler(signal, frame):
    print('\n\nYOU CAN HAZ CTRL+C!\n\n')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# All the regions we should be scanning
__regions = ['eu-west-1', 'eu-west-2','eu-west-3', 'eu-central-1', 'us-east-1', 'us-east-2','us-west-1','us-west-2','ca-central-1','ap-southeast-1','ap-southeast-2','ap-northeast-1','ap-northeast-2','ap-northeast-3','ap-south-1','sa-east-1']

__verbose = False
__nodefault = False

def get_property_func(key):
    """
    Get the accessor function for an instance to look for `key`.

    Look for it as an attribute, and if that does not work, look to see if it
    is a tag.
    """
    aliases = {
        'ip': 'ip_address',
        'private_ip': 'private_ip_address',
    }
    unaliased_key = aliases.get(key, key)

    def get_it(obj):
        try:
            return getattr(obj, unaliased_key)
        except AttributeError:
            if key == 'name':
                return obj.tags.get('Name')
            return obj.tags.get(key)
    return get_it

def get_tags(obj, name):
    try:
        for y in obj['Tags']:
            if y['Key'] == name:
                return y['Value']
    except:
        return ""

def get_tagset(obj, name):
    try:
        for y in obj['TagSet']:
            if y['Key'] == name:
                return y['Value']
    except:
        return ""

def get_taglist(obj, name):
    try:
        for y in obj['TagList']:
            if y['Key'] == name:
                return y['Value']
    except:
        return ""

def elb_get_tags(conn, name, tag):
    response = conn.describe_tags(LoadBalancerNames=[name])
    return get_tags(response['TagDescriptions'][0], tag)

def s3_get_tags(conn, name, tag):
    try:
        response = conn.get_bucket_tagging(Bucket=name)
        return get_tagset(response, tag)
    except:
        return ""

def get_try (x, attr, ret=""):
    try:
        return x[attr]
    except:
        return ret

def elasticache_get_tags(conn, name, tag):
    try:
        response = conn.list_tags_for_resource(ResourceName=name)
        return get_taglist(response, tag)
    except:
        return ""

def filter_key(filter_args):
    def filter_instance(instance):
        return all([value == get_property_func(key)(instance)
            for key, value in filter_args.items()])
    return filter_instance

def print_result( title, table, headers=None ):
    if __verbose:
        print title
    if table:
        print '\n=== %s ===\n' % title
        print tabulate(table, headers)


def process_list(instances, to_row, sort_by=None, filter_by=None):
    if sort_by:
        instances.sort(key=get_property_func(sort_by))
    if filter_by:
        instances = filter(filter_key(filter_by), instances)  # XXX overwriting original
    return map(to_row, instances)


def get_options(input_args, headers=None):
    if headers is None:
        headers = ()
    sort_by = None  # WISHLIST have a tuple
    filter_by_kwargs = {}
    for arg in input_args:
        if arg.startswith('-'):
            # ignore options
            continue
        if '=' in arg:
            key, value = arg.split('=', 2)
            if key not in headers:
                exit('{} not valid'.format(key))
            filter_by_kwargs[key] = value
        elif arg in headers:
            sort_by = arg
        else:
            print 'skipped', arg
    return sort_by, filter_by_kwargs


def list_ec2(region, input_args=""):
    headers = (
        'name',
        'environment',
        'state',
        'ip',
        'private_ip',
        'launch_time',
        'id',
    )
    sort_by, filter_by_kwargs = get_options(input_args, headers)

    try:
      conn = boto3.client('ec2', region)
      instances = conn.describe_instances()
      instanc = [i for r in instances['Reservations'] for i in r['Instances']]
      to_row = lambda x: (
        get_tags(x, 'Name'),
        get_tags(x, 'Environment'),
        x['State']['Name'],
        get_try(x, 'PublicIpAddress'),
        get_try(x, 'PrivateIpAddress'),
        x['LaunchTime'],  #.split('T', 2)[0],
        x['InstanceId'],
      )
      print_result("EC2 @  '%s'" % region,
        process_list(instanc, to_row=to_row, sort_by=sort_by, filter_by=filter_by_kwargs), headers)
    except:
      logging.error( "Unexpected error: %s", sys.exc_info() )


def list_elb(region, input_args=""):
    headers = (
        'name',
        'environment',
        'created_time',
    )
    sort_by, filter_by_kwargs = get_options(input_args, headers)

    # response = conn.describe_tags(LoadBalancerNames=[name])
    try:
      conn = boto3.client('elb', region)
      instances = conn.describe_load_balancers()

      to_row = lambda x: (
        x['LoadBalancerName'],
        elb_get_tags(conn, x['LoadBalancerName'], 'Environment'),
        x['CreatedTime']
      )
      print_result("EC2:ELB @  '%s'" % region,
        process_list(instances['LoadBalancerDescriptions'], to_row=to_row, sort_by=sort_by, filter_by=filter_by_kwargs), headers )
    except:
      logging.error( "Unexpected error: %s", sys.exc_info() )

def list_volume(region, input_args=""):
    headers = (
        'id',
        'size',
        'status',
        'created_time',
    )
    sort_by, filter_by_kwargs = get_options(input_args, headers)

    try:
      conn = boto3.client('ec2', region)
      instances = conn.describe_volumes()
      to_row = lambda x: (
        x['VolumeId'],
        x['Size'],
        x['State'],
        x['CreateTime'],
      )
      print_result("EC2:Volumes @  '%s'" % region,
        process_list(instances['Volumes'], to_row=to_row, sort_by=sort_by, filter_by=filter_by_kwargs), headers )
    except:
      logging.error( "Unexpected error: %s", sys.exc_info() )

def list_elasticache(region, input_args=""):
    headers = (
        'cluster id',
        'engine',
        'status',
        'environment',
        'created_time'
    )
    sort_by, filter_by_kwargs = get_options(input_args, headers)

    try:
      conn = boto3.client('elasticache', region)
      instances = conn.describe_cache_clusters()
      to_row = lambda x: (
        x['CacheClusterId'],
        x['Engine'],
        x['CacheClusterStatus'],
        elasticache_get_tags(conn, 'arn:aws:elasticache:'+region+':781369435176:cluster:'+x['CacheClusterId'], 'Environment'),
        x['CacheClusterCreateTime']
      )
      print_result("ElastiCache @  '%s'" % region,
        process_list(instances['CacheClusters'], to_row=to_row, sort_by=sort_by, filter_by=filter_by_kwargs), headers )
    except:
      logging.error( "Unexpected error: %s", sys.exc_info() )

def list_vpc(region, input_args=""):
    headers = (
        'id',
        'name',
        'default',
        'environment',
        'cidr_block'
    )
    sort_by, filter_by_kwargs = get_options(input_args, headers)

    if __nodefault:
      filter="{'Name':'isDefault','Values':[False]}"

    try:
      conn = boto3.client('ec2', region)
      if __nodefault:
        instances = conn.describe_vpcs(Filters=[filter],)
      else:
        instances = conn.describe_vpcs()

      to_row = lambda x: (
        x['VpcId'],
        get_tags(x,'Name'),
        x['IsDefault'],
        get_tags(x,'Environment'),
        x['CidrBlock']
      )
      print_result("VPC @  '%s'" % region,
        process_list(instances['Vpcs'], to_row=to_row, sort_by=sort_by, filter_by=filter_by_kwargs), headers )
    except:
      logging.error( "Unexpected error: %s", sys.exc_info() )

def list_sg(region, input_args=""):
    headers = (
        'id',
        'name',
        'environment',
    )
    sort_by, filter_by_kwargs = get_options(input_args, headers)

    try:
      conn = boto3.client('ec2', region)
      instances = conn.describe_security_groups()
      to_row = lambda x: (
        x['GroupId'],
        x['GroupName'],
        get_tags(x,'Name'),
        get_tags(x,'Environment')
      )
      print_result("EC2:SG @  '%s'" % region,
        process_list(instances['SecurityGroups'], to_row=to_row, sort_by=sort_by, filter_by=filter_by_kwargs), headers )
    except:
      logging.error( "Unexpected error: %s", sys.exc_info() )

def list_dbss(region, input_args=""):
    headers = (
        'SS id',
        'DB id',
        'engine',
        'create time'
    )
    sort_by, filter_by_kwargs = get_options(input_args, headers)

    try:
      conn = boto3.client('rds', region)
      instances = conn.describe_db_snapshots()
      to_row = lambda x: (
        x['DBSnapshotIdentifier'],
        x['DBInstanceIdentifier'],
        x['Engine'],
        x['SnapshotCreateTime']
      )
      print_result("RDS:Snapshots @  '%s'" % region,
        process_list(instances['DBSnapshots'], to_row=to_row, sort_by=sort_by, filter_by=filter_by_kwargs), headers )
    except:
      logging.error( "Unexpected error: %s", sys.exc_info() )


def list_ec2ss(region, input_args=""):
    headers = (
        'SS id',
        'state',
        'environment',
        'size',
        'create time'
    )
    sort_by, filter_by_kwargs = get_options(input_args, headers)

    try:
      conn = boto3.client('ec2', region)
      instances = conn.describe_snapshots(Filters=[{ 'Name': 'owner-alias', 'Values' : ['self'] }])
      to_row = lambda x: (
        x['SnapshotId'],
        x['State'],
        get_tags(x,'Environment'),
        x['VolumeSize'],
        x['StartTime']
      )
      print_result("EC2:Snapshots @  '%s'" % region,
        process_list(instances['Snapshots'], to_row=to_row, sort_by=sort_by, filter_by=filter_by_kwargs), headers )
    except:
      logging.error( "Unexpected error: %s", sys.exc_info() )

def list_ecss(region, input_args=""):
    headers = (
        'SS name',
        'state',
        'source'
    )
    sort_by, filter_by_kwargs = get_options(input_args, headers)

    try:
      conn = boto3.client('elasticache', region)
      instances = conn.describe_snapshots()
      to_row = lambda x: (
        x['SnapshotName'],
        x['SnapshotStatus'],
        x['SnapshotSource']
      )
      print_result("ElasticCache:Snapshots @  '%s'" % region,
        process_list(instances['Snapshots'], to_row=to_row, sort_by=sort_by, filter_by=filter_by_kwargs), headers )
    except:
      logging.error( "Unexpected error: %s", sys.exc_info() )



def list_rds(region, input_args=""):
    to_row = lambda x: (
        get_try(x, 'DBName', '???'),
        x['DBInstanceIdentifier'],
        x['Engine']+'://'+x['MasterUsername']+"@"  #+x['Endpoint']['Address']+":"+['Endpoint']['Port']+"/"+get_try(x, 'DBName', '???')
    )

    headers = (
        'dbname',
        'id',
        'uri',  # derived
    )
    sort_by, filter_by_kwargs = get_options(input_args, headers)

    try:
      conn = boto3.client('rds', region)
      instances = conn.describe_db_instances()
      print_result( "RDS @  '%s'" % region,
        process_list(instances['DBInstances'], to_row=to_row, sort_by=sort_by, filter_by=filter_by_kwargs), headers )
    except:
      logging.error( "Unexpected error: %s", sys.exc_info() )

def list_s3(input_args=""):
    headers = (
        'name',
        'region',
        'environment',
        'created_time',
    )
    sort_by, filter_by_kwargs = get_options(input_args, headers)

    conn = boto3.client('s3')
    instances = conn.list_buckets()

    try:
      to_row = lambda x: (
        x['Name'],
        (conn.get_bucket_location(Bucket=x['Name'])['LocationConstraint'] or 'us-east-1').replace('EU','eu-west-1'),
        s3_get_tags(conn, x['Name'], 'Environment'),
        x['CreationDate']
      )
      print_result("S3 @ 'worldwide'",
        process_list(instances['Buckets'], to_row=to_row, sort_by=sort_by, filter_by=filter_by_kwargs), headers )
    except:
      logging.error( "Unexpected error: %s", sys.exc_info() )


def _create_parser():
        parser = argparse.ArgumentParser(
            prog='aws-inventory',
            description='CLI to list inventory in AWS')
        parser.add_argument("-V", "--version", action="version",
                            version="{}".format(__version__))
        parser.add_argument('-r', '--region', nargs='+', help='list of AWS Regions to collect from')
        parser.add_argument('command', choices=['all', 'ec2','vpc','elb','rds','elasticache','sg','s3','volume','ec2ss','dbss'])
        parser.add_argument('-v', '--verbose', action="store_true")
        parser.add_argument('-nd', '--nodefault', help="skip defaut VPCs", action="store_true")
        return parser

def main():
    parser = _create_parser()
    _parsed_args = parser.parse_args()

    if _parsed_args.command == 's3':
      list_s3()
      exit()


    if _parsed_args.region:
       regions = _parsed_args.region
    else:
       regions = __regions
       
    global __verbose
    if _parsed_args.verbose:
       __verbose = True

    global __nodefault
    if _parsed_args.nodefault:
       __nodefault = True

    for _region in regions:
       globals()['list_'+_parsed_args.command](_region)


if __name__ == '__main__':
    main()

