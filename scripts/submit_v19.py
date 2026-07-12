import subprocess
import time
import sys

kernel = 'drakus74/atabey-adaptive-baseline'
version = '17'
cmd_status = f'kaggle kernels status {kernel}'
cmd_submit = f'kaggle competitions submit -c biohub-cell-tracking-during-development -f submission.csv -m "V19 watershed refinement: profile-based routing, 6bba-only CFAR+sidelobe cap 900, with centroid watershed refinement." -k {kernel} -v {version}'

print(f'Waiting for {kernel} version {version} to complete...')

while True:
    try:
        res = subprocess.check_output(cmd_status, shell=True, text=True)
        if 'COMPLETE' in res:
            print('Kernel complete! Submitting...')
            submit_res = subprocess.check_output(cmd_submit, shell=True, text=True, stderr=subprocess.STDOUT)
            print(submit_res)
            break
        elif 'ERROR' in res or 'FAILED' in res:
            print('Kernel failed!')
            print(res)
            sys.exit(1)
        else:
            time.sleep(30)
    except Exception as e:
        print(f'Error checking status: {e}')
        time.sleep(30)
