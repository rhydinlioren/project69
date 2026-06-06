#!/usr/bin/env python3
import os
import subprocess
import glob

RAM = "8G"

BASE = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.join(BASE, "minecraft_server")

jars = glob.glob(os.path.join(server_dir, "*.jar"))
if not jars:
    print(f"No jar found in {server_dir}")
    exit(1)

jar_path = jars[0]
eula_path = os.path.join(server_dir, "eula.txt")

if not os.path.exists(eula_path) or "eula=true" not in open(eula_path).read():
    with open(eula_path, "w") as f:
        f.write("eula=true\n")

print(f"Starting {os.path.basename(jar_path)} with {RAM} RAM...")
subprocess.run(["java", f"-Xms{RAM}", f"-Xmx{RAM}", "-jar", jar_path, "nogui"], cwd=server_dir)
