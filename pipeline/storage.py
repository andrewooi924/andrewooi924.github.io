"""R2 upload uses a bucket-scoped S3 token supplied through environment secrets."""
import os
import boto3

def client():
    account=os.environ['CLOUDFLARE_ACCOUNT_ID']
    if not account.isalnum():raise ValueError('Invalid Cloudflare account ID')
    return boto3.client('s3',endpoint_url=f'https://{account}.r2.cloudflarestorage.com',
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],region_name='auto')
