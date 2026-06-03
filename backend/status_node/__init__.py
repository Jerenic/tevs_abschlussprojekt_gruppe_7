"""Verteilte StatusNode des TEVS-Commandcenters.

Die Node ist in fachliche Module aufgeteilt:

- ``config``      Laufzeitkonfiguration (Env/CLI): Port, Peers, DB-Pfad, Intervalle.
- ``models``      Validierung, Zeitstempel-Parsing und Last-Writer-Wins-Vergleich.
- ``storage``     SQLite-Persistenz und In-Memory-Lesecache.
- ``replication`` Peer-Replikation, Pending-Queue und Retry-Worker.
- ``bootstrap``   Snapshot-Abruf, Initial-Sync und Grace-Period-Status.
- ``app``         Flask-App, Routes und Start-Einstiegspunkt.
"""
