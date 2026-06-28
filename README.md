# bitTorrent_client

# Resources
"https://medium.com/@abhinavcv007/bittorrent-part-1-the-engineering-behind-the-bittorrent-protocol-04e70ee01d58"
"https://www.bittorrent.org/beps/bep_0003.html"


```
.torrent file ──bencoded──► Metainfo parser
                                │
                                ├── tracker URL
                                ├── file information
                                ├── piece SHA-1 hashes
                                └── info_hash
                                      │
                                      ▼
Tracker announce URL ──HTTP GET──► Existing tracker server
                                      │
                             bencoded response
                                      │
                                      ▼
                                Peer addresses
                                      │
                                      ▼
                           Peer-wire protocol over TCP
                           (custom binary, not bencode)
```