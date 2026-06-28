# bitTorrent_client

# Resources
"https://medium.com/@abhinavcv007/bittorrent-part-1-the-engineering-behind-the-bittorrent-protocol-04e70ee01d58"
"https://www.bittorrent.org/beps/bep_0003.html"

# Architecture
```
.torrent file
      │
      ▼
Bencode decoder
      │
      ▼
Metainfo parser
      │
      ├── Tracker URL
      ├── File name and size
      ├── Piece size
      ├── Piece SHA-1 hashes
      └── Torrent info hash
              │
              ▼
      Tracker announce URL
              │
              ▼
        HTTP tracker request
              │
              ▼
     Bencoded tracker response
              │
              ▼
        Peer IPs and ports
```