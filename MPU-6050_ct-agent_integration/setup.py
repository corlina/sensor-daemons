import subprocess
import zipfile
import os


for parent, dirs, files in os.walk('ct_addons'):
    for filename in files:
        if filename.endswith('.pyc'):
            filepath = os.path.join(parent, filename)
            print('removing: ' + filepath)
            os.remove(filepath)


try:
    os.remove('ct_addons.zip')
except:
    pass
subprocess.check_call('zip -r ct_addons.zip ct_addons', shell=True)

with zipfile.ZipFile('ct_addons.zip', 'a') as zf:
    zf.write('ct_addons/__main__.py', '__main__.py')
