import requests
r=requests.get('http://localhost:8001/ejecutar-agente/0x0000000000000000000000000000000000000000', stream=True)
print(r.status_code)
for line in r.iter_lines(decode_unicode=True):
    if line:
        print(line)
