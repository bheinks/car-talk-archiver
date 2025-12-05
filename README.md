# Car Talk Archiver

A script that generates an RSS XML feed containing every Car Talk episode currently hosted by NPR, dating back to 2007. Host via HTTP and update with a program like crontab for maximum effect.

Compatible with any podcast application that supports RSS.

## Requirements
```
python = "^3.13"
beautifulsoup4 = "^4.14.3"
feedgen = "^1.0.0"
requests = "^2.32.5"
lxml = "^6.0.2"
```

## Installation
```
pip install car-talk-archiver
```

## Usage
```
usage: cta.py [-h] [-i file] [-o file]

Generate a podcast RSS feed containing every Car Talk episode currently hosted by NPR.

options:
  -h, --help            show this help message and exit
  -i file, --input file
                        file name of an existing feed (if specified, script will only check for newer episodes)
  -o file, --output file
                        output file name (defaults to cartalk_<timestamp>.xml in current working directory)
```

## Examples
Generate a new feed:
```
$ ./cta.py
```

Use an existing feed to generate a new feed including the most recent episodes:
```
$ ./cta.py -i cartalk.xml
```

Update and overwrite an existing feed with the most recent episodes:
```
$ ./cta.py -i cartalk.xml -o cartalk.xml
```