sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y git libpq-dev python-dev python-pip nginx redis-server uwsgi

sudo pip install virtualenv
git clone git@bitbucket.org:fredley/lanes.git

cd lanes

virtualenv env
source env/bin/activate

pip install -r requirements.txt

redis-cli config set notify-keyspace-events Kx
