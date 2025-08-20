#!/usr/bin/env python3
# las_to_copc.py
# Convert LAS -> COPC (.copc.laz) using PDAL pipeline
# Usage:
#   python las_to_copc.py input.las
#   python las_to_copc.py /path/to/folder --glob "*.las" --workers 4
#   python las_to_copc.py input.las --in-srs EPSG:32647 --out-srs EPSG:4978
#   python las_to_copc.py input.las --scale 0.001 0.001 0.001 --offset auto auto auto
#
# Output files will be named <input>.copc.laz (or same name in output dir)

import argparse
import json
import os
import sys
import subprocess
import tempfile
import time
from glob import glob
from multiprocessing import Pool, cpu_count
from pathlib import Path

def check_pdal():
    try:
        out = subprocess.check_output(["pdal", "--version"], text=True)
        return out.strip()
    except Exception as e:
        print("ERROR: ไม่พบ PDAL ในระบบ (ต้องติดตั้งก่อน เช่น conda install -c conda-forge pdal)")
        sys.exit(1)

def build_pipeline(
    input_path: str,
    output_path: str,
    in_srs: str = None,
    out_srs: str = None,
    scale=None,
    offset=None,
):
    pipeline = [input_path]

    if in_srs or out_srs:
        if not in_srs:
            in_srs = "readers.las"
        pipeline.append({
            "type": "filters.reprojection",
            "in_srs": in_srs if in_srs != "readers.las" else None,
            "out_srs": out_srs if out_srs else None
        })
        pipeline[-1] = {k:v for k,v in pipeline[-1].items() if v}

    writers_copc = {
        "type": "writers.copc",
        "filename": output_path
    }

    if scale:
        writers_copc["scale_x"] = float(scale[0])
        writers_copc["scale_y"] = float(scale[1])
        writers_copc["scale_z"] = float(scale[2])

    if offset:
        def parse_off(v):
            return v if str(v).lower() == "auto" else float(v)
        writers_copc["offset_x"] = parse_off(offset[0])
        writers_copc["offset_y"] = parse_off(offset[1])
        writers_copc["offset_z"] = parse_off(offset[2])

    pipeline.append(writers_copc)
    return {"pipeline": pipeline}

def run_pipeline(pipeline_dict):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
        json.dump(pipeline_dict, tf, indent=2)
        tmp_path = tf.name
    try:
        subprocess.check_call(["pdal", "pipeline", tmp_path])
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

def convert_one(args):
    (infile, outdir, in_srs, out_srs, scale, offset, overwrite) = args
    infile = Path(infile)
    if not infile.exists():
        return (infile, False, "ไม่พบไฟล์", 0.0)

    outdir = Path(outdir) if outdir else infile.parent
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / (infile.stem + ".copc.laz")

    if outfile.exists() and not overwrite:
        return (infile, True, f"ข้าม (มีไฟล์อยู่แล้ว): {outfile.name}", 0.0)

    pipeline = build_pipeline(
        str(infile),
        str(outfile),
        in_srs=in_srs,
        out_srs=out_srs,
        scale=scale,
        offset=offset
    )

    start_time = time.time()
    try:
        run_pipeline(pipeline)
        elapsed = time.time() - start_time
        return (infile, True, f"OK -> {outfile.name}", elapsed)
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start_time
        return (infile, False, f"PDAL error (exit {e.returncode})", elapsed)
    except Exception as e:
        elapsed = time.time() - start_time
        return (infile, False, f"Error: {e}", elapsed)

def gather_inputs(path, pattern):
    p = Path(path)
    if p.is_dir():
        files = sorted(glob(str(p / pattern)))
    else:
        files = [str(p)]
    files = [f for f in files if Path(f).suffix.lower() in [".las", ".laz"]]
    return files

def fmt_time(sec: float):
    if sec < 60:
        return f"{sec:.1f}s"
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{int(h)}h {int(m)}m {int(s)}s"
    return f"{int(m)}m {int(s)}s"

def main():
    parser = argparse.ArgumentParser(description="Convert LAS/LAZ to COPC (.copc.laz) via PDAL")
    parser.add_argument("path", help="พาธไฟล์ .las/.laz หรือโฟลเดอร์")
    parser.add_argument("--glob", default="*.las", help="แพทเทิร์นไฟล์เมื่อ path เป็นโฟลเดอร์ (ค่าเริ่มต้น: *.las)")
    parser.add_argument("-o", "--outdir", default=None, help="โฟลเดอร์ผลลัพธ์ (ถ้าไม่ระบุ ใช้โฟลเดอร์เดียวกับไฟล์อินพุต)")
    parser.add_argument("--in-srs", dest="in_srs", default=None, help="EPSG ของอินพุต (เช่น EPSG:32647)")
    parser.add_argument("--out-srs", dest="out_srs", default=None, help="EPSG ของผลลัพธ์ (เช่น EPSG:4978)")
    parser.add_argument("--scale", nargs=3, metavar=("SX","SY","SZ"), default=None, help="scale_x scale_y scale_z (เช่น 0.001 0.001 0.001)")
    parser.add_argument("--offset", nargs=3, metavar=("OX","OY","OZ"), default=None, help="offset_x offset_y offset_z (ใส่ 'auto' ได้)")
    parser.add_argument("--workers", type=int, default=1, help="จำนวน process รันขนาน")
    parser.add_argument("--overwrite", action="store_true", help="เขียนทับไฟล์ที่มีอยู่แล้ว")
    args = parser.parse_args()

    print("ตรวจสอบ PDAL ...")
    ver = check_pdal()
    print(f"พบ PDAL: {ver}")

    files = gather_inputs(args.path, args.glob)
    if not files:
        print("ไม่พบไฟล์อินพุต (.las/.laz)")
        sys.exit(1)

    print(f"เตรียมแปลง {len(files)} ไฟล์ → COPC (.copc.laz)")
    work = [
        (f, args.outdir, args.in_srs, args.out_srs, args.scale, args.offset, args.overwrite)
        for f in files
    ]

    workers = max(1, args.workers if args.workers else 1)
    if workers == 1:
        results = [convert_one(x) for x in work]
    else:
        workers = min(workers, cpu_count())
        with Pool(processes=workers) as pool:
            results = pool.map(convert_one, work)

    ok = sum(1 for _, s, _, _ in results if s)
    ng = len(results) - ok
    for f, s, msg, elapsed in results:
        print(f"[{'OK' if s else 'NG'}] {Path(f).name} : {msg}  (ใช้เวลา {fmt_time(elapsed)})")

    print(f"\nสรุป: สำเร็จ {ok} | ไม่สำเร็จ {ng}")
    sys.exit(0 if ng == 0 else 2)

if __name__ == "__main__":
    main()
