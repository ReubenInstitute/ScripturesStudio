#!/bin/sh
# Run this before committing. Bumps the version to match the commit
# count your commit is about to produce (current count + 1), so once
# committed, the version in debian/changelog is exactly correct.
# Usage: debian/bump-version.sh
set -eu

cd "$(dirname "$0")/.."

VERSION="0.$(($(git rev-list --count HEAD) + 1))"

sed -i "1s/^scripturesstudio (.*)/scripturesstudio ($VERSION)/" debian/changelog

echo "Bumped to $VERSION"
