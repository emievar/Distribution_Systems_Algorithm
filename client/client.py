import sys
import socket

def read_line(sock): # Reads a line from the socket until a newline character is found
    data = b""
    while not data.endswith(b"\n"):
        more = sock.recv(1)
        if not more:
            raise EOFError("Socket closed") # If no more data is received, raise an error
        data += more
    decoded = data.decode()
    print(f"[RECV] {decoded.strip()}")
    return decoded

def send(sock, msg): # Sends a message to the server, ensuring it ends with a newline character
    if not msg.endswith("\n"):
        msg += "\n"
    sock.sendall(msg.encode())
    print(f"[SEND] {msg.strip()}")

def parse_jobs(job_msg): # Parses a job message and returns a dictionary with job details
    parts = job_msg.split()
    return {
        'id': int(parts[1]),
        'submit_time': int(parts[2]),
        'cores': int(parts[3]),
        'memory': int(parts[4]),
        'disk': int(parts[5]),
        'est_runtime': int(parts[6]),
    }

def parse_server_line(line): # Parses a server line and returns a tuple with server details
    return line.strip().split()

def get_servers(sock, job): # Retrieves available servers based on job requirements
    send(sock, f"GETS Avail {job['cores']} {job['memory']} {job['disk']}")
    response = read_line(sock)
    if response.startswith("DATA"):
        num_records = int(response.split()[1])
        if num_records == 0:
            send(sock, "OK")
            final = read_line(sock)
            if final.strip() != ".":
                print(f"[ERR] Expected '.', but got: {final}")
            print("No available servers found")
        else:
            send(sock, "OK")
            servers = []
            for _ in range(num_records):
                server_line = read_line(sock)
                if server_line.strip() == ".":
                    break
                servers.append(parse_server_line(server_line))
            send(sock, "OK")
            final = read_line(sock)
            if final.strip() != ".":
                print(f"[ERR] Expected '.', but got: {final}")
            if servers:
                print(f"Found {len(servers)} available servers.")
                return servers

    print("No available servers found.")
    send(sock, f"GETS Capable {job['cores']} {job['memory']} {job['disk']}")
    response = read_line(sock)
    if not response.startswith("DATA"):
        print(f"[ERR] Server error for GETS Capable: {response.strip()}")
        return []
    num_records = int(response.split()[1])
    send(sock, "OK")
    servers = []
    for _ in range(num_records):
        server_line = read_line(sock)
        if server_line.strip() == ".":
            break
        servers.append(parse_server_line(server_line))
    send(sock, "OK")
    final = read_line(sock)
    if final.strip() != ".":
        print(f"[ERR] Expected '.', but got: {final}")
    return servers

def get_ejwt(sock, server_type, server_id): # Retrieves the estimated job wait time (EJWT) for a specific server
    send(sock, f"EJWT {server_type} {server_id}")
    response = read_line(sock)
    try:
        return int(response.strip())
    except ValueError:
        return float('inf')

def pick_least_wait_server(sock, servers, job=None): # Picks the server with the least estimated job wait time (EJWT)
    scored_servers = []
    for server in servers:
        wait_time = get_ejwt(sock, server[0], server[1]) # Get the estimated job wait time for the server
        print(f"Server {server[0]} {server[1]} wait time: {wait_time}")
        if wait_time == 0:
            print(f"Using {server[0]} {server[1]}")
            return server

        if job:
            cores = int(server[4])
            mem = int(server[5])
            disk = int(server[6])
            over_provision = ((cores - job['cores']) * 1.0 + (mem - job['memory']) / 1000.0 + (disk - job['disk']) / 1000.0) # Calculate over-provisioning
            score = wait_time + over_provision
        else:
            score = wait_time

        scored_servers.append((score, server)) # Append the score and server details to the list

    scored_servers.sort(key=lambda x: (x[0], int(x[1][4]), int(x[1][5]), int(x[1][6])))
    return scored_servers[0][1] if scored_servers else None

def schedule_jobs(): # Main function to connect to the server and schedule jobs
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect(('localhost', 50000))
        print("Connected to server on port 50000")

        send(sock, "HELO")
        read_line(sock)

        send(sock, f"AUTH Dickson")
        read_line(sock)

        send(sock, "REDY")
        msg = read_line(sock)

        while msg.strip() != "NONE":
            if msg.startswith("JOBN"):
                job = parse_jobs(msg)
                print(f"Job received: {job}")
                servers = get_servers(sock, job)
                if not servers:
                    print("[ERR] No capable servers found.")
                    send(sock, "REDY")
                    msg = read_line(sock)
                    continue
                print(f"Servers capable: {len(servers)}")
                target_server = pick_least_wait_server(sock, servers, job)
                print(f"Chosen server: {target_server}")
                send(sock, f"SCHD {job['id']} {target_server[0]} {target_server[1]}")
                read_line(sock)
            send(sock, "REDY")
            msg = read_line(sock)

        send(sock, "QUIT")
        read_line(sock)

if __name__ == '__main__':
    schedule_jobs()
