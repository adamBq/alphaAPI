#!/bin/bash
set -e

# Usage validation
if [ -z "$1" ]; then
    echo "Usage ./deploy.sh [test|dev|prod]"
    exit 1
fi

ENV=$1

# Validate environment input
if [[ ${ENV} != "test" && ${ENV} != "dev" && ${ENV} != "prod" ]]; then
    echo "Invalid environment: '${ENV}'"
    echo "Usage ./deploy.sh [test|dev|prod]"
    exit 1
fi

echo "Starting root deployment for environemnt: $ENV"
echo "----------------------------------------------"

# Find and run deploy.sh in each service folder
for dir in */; do
    if [ -f "${dir}/deploy.sh" ]; then
        echo "Deploying service: $dir"
        chmod +x "$dir/deploy.sh"
        pushd "$dir" > /dev/null
        ./deploy.sh $ENV
        popd > /dev/null
        echo ""
    else
        echo "Skipping $dir: No deploy.sh found"
    fi
done

echo "All services deployed to $ENV environment."
