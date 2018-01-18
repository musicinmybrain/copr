# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure(2) do |config|

  ###  FRONTEND  ###################################################
  config.vm.define "frontend" do |frontend|
    frontend.vm.box = "fedora/25-cloud-base"

    frontend.vm.network "forwarded_port", guest: 80, host: 5000

    #frontend.vm.synced_folder ".", "/vagrant", type: "nfs"
    frontend.vm.synced_folder ".", "/vagrant", type: "rsync" # nfs sync does not with f25 currently due to Bug 1415496 - rpcbind fails at boot

    frontend.vm.network "private_network", ip: "192.168.242.51"

    # Update the system
    frontend.vm.provision "shell",
      inline: "sudo dnf clean all && sudo dnf -y update || true" # || true cause dnf might return non-zero status (probly delta rpm rebuilt failed)

    # Install packages to support Copr and building RPMs
    frontend.vm.provision "shell",
      inline: "sudo dnf -y install dnf-plugins-core tito wget"

    # Enable the Copr repository for dependencies
    #frontend.vm.provision "shell",
      # inline: "sudo dnf -y copr enable msuchy/copr"
      # WORKAROUND: old DNF plugin uses outdated .repo URL
    #  inline: "sudo wget https://copr.fedoraproject.org/coprs/msuchy/copr/repo/fedora-21/msuchy-copr-fedora-21.repo -P /etc/yum.repos.d/"

    frontend.vm.provision "shell",
      inline: "sudo dnf -y copr enable @copr/copr"

    frontend.vm.provision "shell",
      inline: "sudo dnf -y copr enable @modularity/modulemd"

    # Install build dependencies for Copr Frontend
    frontend.vm.provision "shell",
      inline: "sudo dnf -y builddep /vagrant/frontend/copr-frontend.spec"

    # Remove previous build, if any
    frontend.vm.provision "shell",
      inline: "sudo rm -rf /tmp/tito",
      run: "always"

    # WORKAROUND: install redis which is needed for %check in spec
    frontend.vm.provision "shell",
      inline: "sudo dnf -y install redis"

    # WORKAROUND: start redis
    frontend.vm.provision "shell",
      inline: "sudo systemctl start redis",
      run: "always"

    # Build Copr Frontend
    frontend.vm.provision "shell",
      inline: "cd /vagrant/frontend/ && tito build --test --rpm --rpmbuild-options='--nocheck'",
      run: "always"

    # Install the Copr Frontend build
    frontend.vm.provision "shell",
      inline: "sudo dnf -y install /tmp/tito/noarch/copr-frontend*.noarch.rpm",
      run: "always"

    # Configure dist git url
    frontend.vm.provision "shell",
      inline: "sed -e 's/^DIST_GIT_URL.*/DIST_GIT_URL = \"http:\\/\\/192.168.242.52\\/cgit\\/\"/' /etc/copr/copr.conf | sudo tee /etc/copr/copr.conf"

    # Configure dist git url
    frontend.vm.provision "shell",
      inline: "sed -e \"s/^#BACKEND_PASSWORD.*/BACKEND_PASSWORD = \\'1234\\'/\" /etc/copr/copr.conf | sudo tee /etc/copr/copr.conf"

    # Configure backend base url
    frontend.vm.provision "shell",
      inline: "sed -e 's/^BACKEND_BASE_URL.*/BACKEND_BASE_URL = \"http:\\/\\/localhost:5002\"/' /etc/copr/copr.conf | sudo tee /etc/copr/copr.conf",
      run: "always"

    # Configure import logs url
    frontend.vm.provision "shell",
      inline: "sed -e 's/^COPR_DIST_GIT_LOGS_URL.*/COPR_DIST_GIT_LOGS_URL = \"http:\\/\\/192.168.242.52\\/per-task-logs\"/' /etc/copr/copr.conf | sudo tee /etc/copr/copr.conf",
      run: "always"

    # ..
    frontend.vm.provision "shell",
      inline: "sudo dnf -y install copr-selinux postgresql-server"

    # ..
    frontend.vm.provision "shell",
      inline: "sudo postgresql-setup initdb"

    # ..
    frontend.vm.provision "shell",
      inline: "sudo systemctl start postgresql",
      run: "always"

    # ..
    frontend.vm.provision "shell",
      inline: "sudo su - postgres -c 'PGPASSWORD=coprpass ; createdb -E UTF8 coprdb ; yes $PGPASSWORD | createuser -P -sDR copr-fe'"

    # I want to prepend some lines to a file - I'll do it in three steps
    # 1.  backup the database config file
    frontend.vm.provision "shell",
      inline: "sudo mv /var/lib/pgsql/data/pg_hba.conf /tmp/pg_hba.conf"

    # 2.  write the lines
    frontend.vm.provision "shell",
      inline: "printf 'local coprdb copr-fe md5\nhost  coprdb copr-fe 127.0.0.1/8 md5\nhost  coprdb copr-fe ::1/128 md5\nlocal coprdb postgres  ident\n' | sudo tee /var/lib/pgsql/data/pg_hba.conf"

    # 3.  write the file back after those lines
    frontend.vm.provision "shell",
      inline: "sudo cat /tmp/pg_hba.conf | sudo tee -a  /var/lib/pgsql/data/pg_hba.conf"

    # ..
    frontend.vm.provision "shell",
      inline: "sudo systemctl reload postgresql"

    # ..
    frontend.vm.provision "shell",
      inline: "cd /usr/share/copr/coprs_frontend/ && sudo ./manage.py create_db --alembic alembic.ini"

    # ..
    frontend.vm.provision "shell",
      inline: "sudo /usr/share/copr/coprs_frontend/manage.py create_chroot fedora-{22,23,rawhide}-{i386,x86_64,ppc64le} epel-{6,7}-x86_64 epel-6-i386"

    # ..
    frontend.vm.provision "shell",
      inline: "echo 'PEERDNS=no' | sudo tee -a /etc/sysconfig/network"

    # ..
    frontend.vm.provision "shell",
      inline: "echo 'nameserver 8.8.8.8' | sudo tee -a /etc/resolv.conf"

    # ..
    frontend.vm.provision "shell",
      inline: "sudo systemctl restart network"

    # ..
    frontend.vm.provision "shell", inline: <<-FOO
  echo \"
  <VirtualHost 0.0.0.0>

      WSGIPassAuthorization On
      WSGIDaemonProcess 127.0.0.1 user=copr-fe group=copr-fe threads=5
      WSGIScriptAlias / /usr/share/copr/coprs_frontend/application
      WSGIProcessGroup 127.0.0.1
      <Directory /usr/share/copr>
          WSGIApplicationGroup %{GLOBAL}
          Require all granted
      </Directory>
  </VirtualHost>
  \" | sudo tee /etc/httpd/conf.d/copr.conf
  FOO

    # ..
    frontend.vm.provision "shell",
      inline: "sudo chown -R copr-fe:copr-fe /usr/share/copr"

    # selinux: make data dir writeable for httpd
    # TODO: probly correct solution is to uncomment first four lines in
    # coprs_frontend/config/copr.conf so that data are stored under /var/lib
    # and not under /usr/share/copr. copr-selinux does not account for storing
    # data under /usr/share/copr/. Discuss this with peers.
    frontend.vm.provision "shell",
      inline: "chcon -R -t httpd_sys_rw_content_t /usr/share/copr/data",
      run: "always"

    # ..
    frontend.vm.provision "shell",
      inline: "sudo chown -R copr-fe:copr-fe /var/log/copr-frontend"

    # ..
    frontend.vm.provision "shell",
      inline: "sudo systemctl restart httpd",
      run: "always"

    frontend.vm.provision "shell", run: "always", inline: <<-EOF
      echo "#########################################################"
      echo "###   Your development instance of Copr Frontend      ###"
      echo "###   is now running at: http://localhost:5000        ###"
      echo "#########################################################"
    EOF

    # workaround
    frontend.vm.provision "shell",
      inline: "sudo setenforce 0 && sudo systemctl restart httpd",
      run: "always"

  end
  ###  DIST-GIT  ###################################################
  config.vm.define "distgit" do |distgit|

    distgit.vm.box = "fedora/25-cloud-base"

    distgit.vm.network "forwarded_port", guest: 80, host: 5001

    #distgit.vm.synced_folder ".", "/vagrant", type: "nfs"
    distgit.vm.synced_folder ".", "/vagrant", type: "rsync" # nfs sync does not with f25 currently due to Bug 1415496 - rpcbind fails at boot

    distgit.vm.network "private_network", ip: "192.168.242.52"

    distgit.vm.provision "shell",
      inline: "sudo dnf -y copr enable clime/dist-git"

    # Update the system
    distgit.vm.provision "shell",
      inline: "sudo dnf clean all && sudo dnf -y update || true" # || true cause dnf might return non-zero status (probly delta rpm rebuilt failed)

    # ...
    distgit.vm.provision "shell",
      inline: "sudo dnf -y install tito cgit dist-git dist-git-selinux pyrpkg || sudo dnf -y upgrade tito cgit dist-git dist-git-selinux pyrpkg"

    # ...
    distgit.vm.provision "shell",
      inline: "sudo dnf builddep -y /vagrant/dist-git/copr-dist-git.spec"

    # ...
    distgit.vm.provision "shell",
      inline: "sudo rm -rf /tmp/tito/*",
      run: "always"

    # ...
    distgit.vm.provision "shell",
      inline: "cd /vagrant/dist-git/ && tito build --test --rpm --rpmbuild-options='--nocheck'",
      run: "always"

    # ...
    distgit.vm.provision "shell",
      inline: "sudo dnf -y install /tmp/tito/noarch/copr-dist-git*.noarch.rpm || sudo dnf -y upgrade /tmp/tito/noarch/copr-dist-git*.noarch.rpm || sudo dnf -y downgrade /tmp/tito/noarch/copr-dist-git*.noarch.rpm",
      run: "always"

    # ...
    distgit.vm.provision "shell", inline: <<-EOF
echo \"[dist-git]
frontend_base_url=http://192.168.242.51
frontend_auth=1234
\" | sudo tee /etc/copr/copr-dist-git.conf && sudo chmod 644 /etc/copr/copr-dist-git.conf
    EOF

    # ...
    distgit.vm.provision "shell", inline: <<-EOF
echo \" [user]
        email = copr-devel@lists.fedorahosted.org
        name = Copr dist git\" | sudo tee /home/copr-dist-git/.gitconfig && sudo chown copr-dist-git:copr-dist-git /home/copr-dist-git/.gitconfig
    EOF

    # ...
    distgit.vm.provision "shell", inline: <<-EOF
echo \"
AliasMatch \\"/repo(/.*)/md5(/.*)\\" \\"/var/lib/dist-git/cache/lookaside\\$1\\$2\\"
Alias /repo/ /var/lib/dist-git/cache/lookaside/
\" | sudo tee /etc/httpd/conf.d/dist-git/lookaside-copr.conf
    EOF

    # ...
    distgit.vm.provision "shell",
      inline: "systemctl restart httpd && systemctl enable httpd"

    # ...
    distgit.vm.provision "shell",
      inline: "sudo sed -i s/^cache-size.*// /etc/cgitrc"

    # ...
    distgit.vm.provision "shell",
      inline: "echo 'scan-path=/var/lib/dist-git/git/rpms' | sudo tee -a /etc/cgitrc"

    # ...
    distgit.vm.provision "shell",
      inline: "sudo systemctl start dist-git.socket && sudo systemctl enable dist-git.socket"

    # ...
    distgit.vm.provision "shell",
      inline: "sudo systemctl start copr-dist-git && sudo systemctl enable copr-dist-git"

    #...
    distgit.vm.provision "shell",
      inline: "sudo systemctl daemon-reload",
      run: "always"

    #...
    distgit.vm.provision "shell",
      inline: "sudo systemctl restart copr-dist-git",
      run: "always"

    distgit.vm.provision "shell", run: "always", inline: <<-EOF
      echo "#########################################################"
      echo "###   Your development instance of Copr Dist Git      ###"
      echo "###   is now running at: http://localhost:5001/cgit   ###"
      echo "#########################################################"
    EOF
  end

  ###  BACKEND   ###################################################
  config.vm.define "backend" do |backend|

    backend.vm.box = "fedora/25-cloud-base"

    backend.vm.network "forwarded_port", guest: 5002, host: 5002

    #backend.vm.synced_folder ".", "/vagrant", type: "nfs"
    backend.vm.synced_folder ".", "/vagrant", type: "rsync" # nfs sync does not with f25 currently due to Bug 1415496 - rpcbind fails at boot

    backend.vm.network "private_network", ip: "192.168.242.53"

    backend.vm.provision "shell",
      inline: <<-SHELL
        sudo dnf -y copr enable @copr/copr-dev
        sudo dnf -y copr enable @modularity/modulemd
        sudo rpm --nodeps -e vim-minimal
        sudo dnf -y install dnf-plugins-core htop tito wget net-tools iputils vim mlocate git sudo python-nova openssh-server supervisor psmisc tmux

        # Builder packages
        sudo dnf -y install fedpkg-copr packagedb-cli fedora-cert mock mock-lvm createrepo yum-utils pyliblzma rsync openssh-clients libselinux-python libsemanage-python rpm glib2 ca-certificates scl-utils-build ethtool copr-keygen nginx

        echo '127.0.0.1 keygen' >> /etc/hosts
      SHELL

    backend.vm.provision "shell", run: "always", inline: <<-SHELL
        sudo dnf builddep -y /vagrant/backend/copr-backend.spec --allowerasing
        sudo rm -rf /tmp/tito/*
        cd /vagrant/backend/ && tito build --test --rpm --rpmbuild-options='--nocheck'
        sudo dnf -y install /tmp/tito/noarch/copr-backend*.noarch.rpm || sudo dnf -y upgrade /tmp/tito/noarch/copr-backend*.noarch.rpm || sudo dnf -y downgrade /tmp/tito/noarch/copr-backend*.noarch.rpm
    SHELL

    backend.vm.provision "shell",
      inline: <<-SHELL
        echo 'root:passwd' | sudo chpasswd
        sudo mkdir /root/.ssh &&  sudo chmod 700 /root /root/.ssh
        sudo touch /root/.ssh/authorized_keys && sudo chmod 600 /root/.ssh/authorized_keys
        sudo ssh-keygen -f /root/.ssh/id_rsa -N '' -q -C root@locahost
        sudo bash -c "cat /root/.ssh/id_rsa.pub >> /root/.ssh/authorized_keys"

        echo 'copr:passwd' | sudo chpasswd
        sudo bash -c "echo 'copr ALL=(ALL:ALL) NOPASSWD:ALL' >> /etc/sudoers"
        sudo mkdir -p /home/copr/.ssh && sudo chmod 700 /home/copr /home/copr/.ssh
        sudo ssh-keygen -f /home/copr/.ssh/id_rsa -N '' -q -C copr@locahost
        sudo touch /home/copr/.ssh/authorized_keys && sudo chmod 600 /home/copr/.ssh/authorized_keys
        sudo bash -c "cat /home/copr/.ssh/id_rsa.pub >> /root/.ssh/authorized_keys"
        sudo bash -c "cat /home/copr/.ssh/id_rsa.pub >> /home/copr/.ssh/authorized_keys"
        sudo chown copr:copr -R /home/copr
        sudo usermod -a -G mock copr

        sudo dnf install -y uwsgi uwsgi-plugin-python
        sudo mkdir /var/log/uwsgi
        sudo chown apache:apache /var/log/uwsgi
        sudo chmod 775 /var/log/uwsgi
        sudo chown apache:apache /var/run/uwsgi
        sudo chmod 775 /var/run/uwsgi
        sudo usermod copr-signer -G apache

        sudo cp -r /vagrant/backend/docker/files/* /
        sudo chmod 700 /root && sudo chmod 700 /home/copr && sudo chown copr:copr /home/copr # fix permission after COPY

        sudo chown copr-signer:apache /etc/uwsgi.d/copr-keygen.ini
        sudo chown copr-signer:copr-signer /var/log/copr-keygen/main.log

        sudo dnf -y downgrade fedpkg # temporary fix cause fedpkg-copr doesn't work with the new version of fedpkg
        sudo dnf -y install ansible1.9 --allowerasing # copr does not support ansible2 yet
      SHELL

    backend.vm.provision "shell",
      inline: <<-SHELL
        sudo sed -i s/localhost:5000/192.168.242.51/ /etc/copr/copr-be.conf
        sudo sed -i s/localhost:5001/192.168.242.52/ /etc/copr/copr-be.conf
        sudo sed -i s/localhost:5001/192.168.242.52/ /etc/rpkg/fedpkg-copr.conf
      SHELL

    backend.vm.provision "shell",
      inline: "sudo echo 4096 > /proc/sys/net/core/somaxconn",
      run: "always"

    backend.vm.provision "shell",
      inline: "sudo /usr/bin/supervisord -c /etc/supervisord.conf",
      run: "always"

    backend.vm.provision "shell", run: "always", inline: <<-EOF
      echo "#########################################################"
      echo "###   Your development instance of Copr Backend       ###"
      echo "###   is now running at: http://localhost:5002        ###"
      echo "#########################################################"
    EOF

  end

end