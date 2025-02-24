import requests

host = "https://api.gateio.ws"
prefix = "/api/v4"
headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

url = '/futures/usdt/contracts'
query_param = ''
r = requests.request('GET', host + prefix + url, headers=headers)
print(r.json())
# Create and write response to file
with open('req_result.txt', 'w') as f:
    f.write(str(r.json()))


print(r.json())