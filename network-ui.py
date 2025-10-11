import os
import shutil
import subprocess
from flask import Flask, render_template
from flask import request
import string
from flask import request, render_template, redirect, url_for
import docker


client = docker.from_env()


import random
app = Flask(__name__)

def get_os_family():
    if os.path.exists("/etc/debian_version"):
        return "debian"
    elif os.path.exists("/etc/redhat-release"):
        return "redhat"
    else:
        return "unknown"



def install_package(tool, os_family):
    package_map = {
        "docker": "docker.io" if os_family == "debian" else "docker",
        "pip3": "python3-pip",
        "python3-venv": "python3-venv",
        "docker-compose": None  # We'll handle it manually
    }

    package_name = package_map.get(tool, tool)

    try:
        if os_family == "debian":
            subprocess.run(["sudo", "apt", "update"], check=True)

            if tool == "terraform":
                subprocess.run(["sudo", "apt", "install", "-y", "wget", "gnupg", "software-properties-common", "curl"], check=True)
                subprocess.run([
                    "wget", "-O", "hashicorp.gpg", "https://apt.releases.hashicorp.com/gpg"
                ], check=True)
                subprocess.run([
                    "gpg", "--dearmor", "--output", "hashicorp-archive-keyring.gpg", "hashicorp.gpg"
                ], check=True)
                subprocess.run([
                    "sudo", "mv", "hashicorp-archive-keyring.gpg", "/usr/share/keyrings/hashicorp-archive-keyring.gpg"
                ], check=True)

                codename = subprocess.check_output(["lsb_release", "-cs"], text=True).strip()
                apt_line = (
                    f"deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] "
                    f"https://apt.releases.hashicorp.com {codename} main\n"
                )
                with open("hashicorp.list", "w") as f:
                    f.write(apt_line)
                subprocess.run(["sudo", "mv", "hashicorp.list", "/etc/apt/sources.list.d/hashicorp.list"], check=True)

                subprocess.run(["sudo", "apt", "update"], check=True)
                subprocess.run(["sudo", "apt", "install", "-y", "terraform"], check=True)

            elif tool == "docker-compose":
                subprocess.run(["sudo", "apt", "install", "-y", "docker-compose"], check=True)

            else:
                subprocess.run(["sudo", "apt", "install", "-y", package_name], check=True)

        elif os_family == "redhat":
            if tool == "terraform":
                subprocess.run(["sudo", "yum", "install", "-y", "yum-utils"], check=True)
                subprocess.run([
                    "sudo", "yum-config-manager", "--add-repo",
                    "https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo"
                ], check=True)
                subprocess.run(["sudo", "yum", "install", "-y", "terraform"], check=True)

            elif tool == "docker-compose":
                subprocess.run(["sudo", "yum", "install", "-y", "docker-compose"], check=True)

            else:
                subprocess.run(["sudo", "yum", "install", "-y", package_name], check=True)

        else:
            return False, "Unsupported OS"

        return True, None

    except Exception as e:
        return False, str(e)




@app.route("/pre-req")
def prereq():
    tools = ["pip3", "openssl", "docker", "terraform","docker-compose"]
    results = {}
    os_family = get_os_family()

    for tool in tools:
        if shutil.which(tool):
            results[tool] = "✅ Installed"
        else:
            success, error = install_package(tool, os_family)
            if success:
                results[tool] = "❌ Not Found → 🛠️ Installed"
            else:
                results[tool] = f"❌ Not Found → ❌ Error: {error}"



    docker_installed = shutil.which("docker") is not None
    return render_template("prereq.html", results=results, os_family=os_family, docker_installed=docker_installed)












# Check if Portainer is actually installed and running (or exists as a container)
def is_portainer_installed():
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", "portainer"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True
        )
        return result.stdout.strip() in ["true", "false"]
    except Exception:
        return False

# Actually run Portainer
def run_portainer():
    try:
        subprocess.run(["docker", "volume", "create", "portainer_data"], check=True)
        subprocess.run([
            "docker", "run", "-d",
            "-p", "9443:9443", "-p", "9000:9000",
            "--name", "portainer",
            "--restart=always",
            "-v", "/var/run/docker.sock:/var/run/docker.sock",
            "-v", "portainer_data:/data",
            "portainer/portainer-ce:latest"
        ], check=True)
        return True, "✅ Portainer installed successfully."
    except subprocess.CalledProcessError as e:
        return False, f"❌ Docker Error: {str(e)}"

# Routes
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/install_portainer", methods=["GET", "POST"])
def install_portainer_route():
    installed = is_portainer_installed()
    portainer_url = "https://localhost:9443"
    message = None

    if request.method == "POST":
        if not installed:
            success, message = run_portainer()
            installed = success
        else:
            message = "ℹ️ Portainer is already installed."

    return render_template("portainer.html", installed=installed, message=message, url=portainer_url)




##################ANSIBLE INSTALLATION##################

@app.route("/network")
def network_info():
    return render_template("network_info.html")


used_ports = set()

def get_random_port(start=4000, end=9000):
    while True:
        port = random.randint(start, end)
        if port not in used_ports:
            used_ports.add(port)
            return port

def generate_random_name(prefix):
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{prefix}-{suffix}"

def create_gns3_compose_file(server_port, gui_port, container_prefix):
    server_name = f"{container_prefix}-server"
    gui_name = f"{container_prefix}-gui"

    os.makedirs("compose_files", exist_ok=True)

    compose_content = f"""
version: '3.8'
services:
  {server_name}:
    image: arunvel1988/gns3-server-v1
    container_name: {server_name}
    restart: always
    network_mode: host
    privileged: true
    ports:
      - "{server_port}:3080"
    environment:
      - GNS3_ENABLE_KVM=False
      - QEMU_ACCEL=tcg
    volumes:
      - {container_prefix}_data:/data
      - ./../gns3_server.conf:/server/conf/gns3_server.conf:rw
      - ./../qemu_vm.py:/server/gns3server/compute/qemu/qemu_vm.py:rw


  {gui_name}:
    image: arunvel1988/ubuntu-desktop-lxde-vnc
    container_name: {gui_name}
    restart: always
    ports:
      - "{gui_port}:80"
    environment:
      - VNC_PASSWORD=ubuntu
      - ALSADEV=hw:2,0
    devices:
      - /dev/snd
    volumes:
      - {container_prefix}_data:/root/GNS3
      - /dev/shm:/dev/shm

volumes:
  {container_prefix}_data:
"""

    file_path = f"compose_files/{container_prefix}.yml"
    with open(file_path, "w") as f:
        f.write(compose_content)

    return file_path, server_name, gui_name, server_port, gui_port

def run_docker_compose(compose_file, container_prefix):
    try:
        subprocess.run(["docker-compose", "-p", container_prefix, "-f", compose_file, "up", "-d"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to run Docker Compose: {e}")
        raise

@app.route("/gns3/create", methods=["GET", "POST"])
def create_gns3():
    if request.method == "POST":
        prefix = request.form["name"].strip() or generate_random_name("gns3")

        # Use get_random_port() if input is empty
        server_port_input = request.form.get("server_port", "").strip()
        gui_port_input = request.form.get("gui_port", "").strip()

        server_port = int(server_port_input) if server_port_input else get_random_port()
        gui_port = int(gui_port_input) if gui_port_input else get_random_port()

        # Create Docker Compose file
        path, server_name, gui_name, s_port, g_port = create_gns3_compose_file(server_port, gui_port, prefix)
        run_docker_compose(path, prefix)

        # Verify containers started
        try:
            server_container = client.containers.get(server_name)
            gui_container = client.containers.get(gui_name)
            if server_container.status != "running" or gui_container.status != "running":
                status_msg = f"⚠️ One or more containers not running. Server: {server_container.status}, GUI: {gui_container.status}"
            else:
                status_msg = "✅ GNS3 containers started successfully!"
        except docker.errors.NotFound as e:
            status_msg = f"❌ Error: {e}"

        return render_template("success.html",
                               os_type="GNS3",
                               container=f"{server_name} & {gui_name}",
                               version="N/A",
                               rdp=s_port,
                               web=g_port,
                               status=status_msg)

    return render_template("gns3_create.html")



@app.route("/gns3/list")
def list_gns3_containers():
    containers = []
    for c in client.containers.list(all=True):  # include stopped too if needed
        try:
            if c.image.tags and (
                "arunvel1988/gns3-server-v1" in c.image.tags[0] or
                "ubuntu-desktop-lxde-vnc" in c.image.tags[0]
            ):
                containers.append({
                    "name": c.name,
                    "status": c.status,
                    "image": c.image.tags[0],
                    "ports": ", ".join([
                        f"{container_port}->{details[0]['HostPort']}"
                        for container_port, details in (c.attrs['NetworkSettings']['Ports'] or {}).items()
                        if details
                    ])
                })
        except Exception as e:
            print(f"[!] Skipped container {c.name} due to error: {e}")
    return render_template("list.html", os_type="GNS3", containers=containers)



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5004, debug=True)
