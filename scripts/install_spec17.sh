#!/bin/bash

set -e

cd "$(dirname "$0")/.."

BASE="$PWD"
SPEC_MNT=/tmp/specmnt
SPEC_DIR="$BASE/spec17"
SPEC_SUPPORT_DIR="$BASE/support_files/spec"
SPEC_ISO="cpu2017-1_0_2.iso"

mkdir -p "$SPEC_DIR"
mkdir -p "$SPEC_MNT"

if [ ! -e "$SPEC_ISO" ]; then
    echo "Please download $SPEC_ISO and place it in the root of the repository, or update SPEC_ISO if your version differs."
    exit 1
fi

sudo mount -o loop,ro "$SPEC_ISO" "$SPEC_MNT"
trap "sudo umount $SPEC_MNT; rm -d $SPEC_MNT" EXIT

pushd "$SPEC_DIR"

tar xvf "$SPEC_MNT"/install_archives/cpu2017.tar.xz

SPEC_INSTALL_ARGS=(-f)

./install.sh "${SPEC_INSTALL_ARGS[@]}"

# Run the self-update

. shrc
yes | runcpu --update

# Install config and evaluation support scripts

mkdir -p releval/scripts
cp "$SPEC_SUPPORT_DIR/spec17.cfg" config/releval.cfg
ln -sfr "$SPEC_SUPPORT_DIR/run.py" releval/
ln -sfr "$SPEC_SUPPORT_DIR/spec_submit.sh" releval/scripts/

popd # $SPEC_DIR
