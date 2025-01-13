#!/bin/bash
mkdir -p ~/.ssh; chmod 700 ~/.ssh
cp $SSH_PRIVATE_KEY_TECH ~/.ssh/id_rsa; chmod 600 ~/.ssh/id_rsa
cp "$OPENSTACK_CLOUDS_FILE" clouds.rc
echo "Secrets prepared."
