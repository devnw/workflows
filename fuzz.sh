#!/bin/bash

fuzzTime=${1:-10}

files=$(grep -r --include='**_test.go' --files-with-matches 'func Fuzz' .)

for file in ${files}
do
	funcs=$(grep -o 'func Fuzz\w*' $file | sed 's/func //')
	for func in ${funcs}
	do
		echo "Fuzzing $func in $file"
		parentDir=$(dirname $file)
		go test $parentDir -run=$func -fuzz=$func -fuzztime=${fuzzTime}s
		if [ $? -ne 0 ]; then
			echo "Fuzzing $func in $file failed"
			exit 1
		fi
	done
done
