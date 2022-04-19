try:
    import usocket as _socket
except:
    import _socket
try:
    import ussl as ssl
except:
    import ssl

    # CPython only supports server_hostname with SSLContext
    ssl = ssl.SSLContext()


def test_one(site, opts):
    ai = _socket.getaddrinfo(site, 443)
    addr = ai[0][-1]

    s = _socket.socket()

    try:
        s.connect(addr)

        if "sni" in opts:
            s = ssl.wrap_socket(s, server_hostname=opts["host"])
        else:
            s = ssl.wrap_socket(s)

        s.write(b"GET / HTTP/1.0\r\nHost: %s\r\n\r\n" % bytes(site, "latin"))
        resp = s.read(4096)
        if resp[:7] != b"HTTP/1.":
            raise ValueError("response doesn't start with HTTP/1.")
        # print(resp)

    finally:
        s.close()


SITES = [
    "google.com",
    "www.google.com",
    "micropython.org",
    "pypi.org",
    "api.telegram.org",
    {"host": "api.pushbullet.com", "sni": True},
]


def main():
    for site in SITES:
        opts = {}
        if isinstance(site, dict):
            opts = site
            site = opts["host"]

        try:
            test_one(site, opts)
            print(site, "ok")
        except Exception as e:
            print(site, e)


main()
