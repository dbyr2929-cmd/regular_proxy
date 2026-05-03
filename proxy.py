import socket
import threading
import os

def relay(source, destination):
    try:
        while True:
            data = source.recv(4096)
            if not data:
                break
            destination.sendall(data)
    except Exception:
        pass
    finally:
        try:
            source.shutdown(socket.SHUT_RD)
        except Exception:
            pass
        try:
            destination.shutdown(socket.SHUT_WR)
        except Exception:
            pass

def handle_client(client_socket):
    try:
        request = client_socket.recv(4096)
        if not request:
            client_socket.close()
            return

        # 1. Handling HTTPS Tunneling (CONNECT method)
        if request.startswith(b'CONNECT'):
            first_line = request.split(b'\n')[0]
            try:
                _, target, _ = first_line.split(b' ')
                target_host, target_port = target.split(b':')
                target_host = target_host.decode('utf-8')
                target_port = int(target_port.decode('utf-8'))
            except Exception:
                client_socket.close()
                return

            try:
                server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server_socket.connect((target_host, target_port))
            except Exception:
                client_socket.send(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                client_socket.close()
                return

            # Tell the browser the tunnel is ready
            client_socket.send(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            
            # Start two-way relay (The 'Pipe')
            thread1 = threading.Thread(target=relay, args=(client_socket, server_socket))
            thread2 = threading.Thread(target=relay, args=(server_socket, client_socket))
            thread1.start()
            thread2.start()
            thread1.join()
            thread2.join()
            
        # 2. Handling standard HTTP (GET/POST etc)
        else:
            first_line = request.split(b'\n')[0]
            try:
                method, url, protocol = first_line.split(b' ')
            except Exception:
                client_socket.close()
                return

            http_pos = url.find(b'://')
            if http_pos != -1:
                url = url[http_pos + 3:]
            
            port = 80
            webserver_pos = url.find(b'/')
            if webserver_pos == -1:
                webserver_pos = len(url)
            
            port_pos = url.find(b':')
            if port_pos != -1 and port_pos < webserver_pos:
                try:
                    port = int(url[port_pos + 1:webserver_pos])
                except ValueError:
                    port = 80
                webserver = url[:port_pos]
            else:
                webserver = url[:webserver_pos]

            try:
                server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server_socket.connect((webserver.decode('utf-8'), port))
                server_socket.sendall(request)
                
                while True:
                    data = server_socket.recv(4096)
                    if data:
                        client_socket.sendall(data)
                    else:
                        break
                server_socket.close()
            except Exception:
                client_socket.close()
                return

    except Exception as e:
        print(f"Error handling client: {e}")
    finally:
        client_socket.close()

def main():
    # Railway provides the port via an environment variable
    listen_port = int(os.environ.get("PORT", 8443))
    listen_addr = '0.0.0.0'
    
    proxy_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    proxy_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    proxy_server.bind((listen_addr, listen_port))
    proxy_server.listen(100) # Increased backlog for stability
    
    print(f"[*] Proxy server active on port {listen_port}")
    print("[*] Note: SSL is handled by the Railway edge router.")

    while True:
        try:
            client_sock, addr = proxy_server.accept()
            # We no longer use ssl_context.wrap_socket here.
            # Railway has already decrypted the outer layer for us.
            client_handler = threading.Thread(target=handle_client, args=(client_sock,))
            client_handler.setDaemon(True)
            client_handler.start()
        except Exception as e:
            print(f"Connection error: {e}")

if __name__ == "__main__":
    main()
