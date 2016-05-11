cd /home/ubuntu/lanes

git checkout .
git pull

pip install -r requirements.txt

./manage.py migrate

sudo mv nginx.conf /etc/nginx/sites-available/default
sudo service nginx restart


