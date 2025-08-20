python las\_to\_copc.py input.las

python las\_to\_copc.py D:\\data --glob "\*.laz" --workers 4 --outdir D:\\data\\copc --overwrite

python las\_to\_copc.py input.las --in-srs EPSG:32647 --out-srs EPSG:4978

python las\_to\_copc.py input.las --scale 0.001 0.001 0.001 --offset auto auto auto

