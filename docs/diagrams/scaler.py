"""
Diagramme (fichier Python pour la librairie `diagrams`)
"""


from diagrams import Diagram, Cluster, Edge
from diagrams.onprem.client import User
from diagrams.onprem.network import Nginx
from diagrams.onprem.compute import Server
from diagrams.onprem.inmemory import Redis
from diagrams.programming.language import Python


# Nombre initial de gateways dans le pool (modifiable)
INITIAL_GATEWAYS = 4

graph_attr = {
    "labelfloat": "true"
}

with Diagram("MediaGW auto scaler", show=False, filename="scaler", outformat="png", direction="LR", graph_attr=graph_attr):
    redis = Redis("Redis")
    with Cluster("MediaGW Gateway Pool"):
        gateways = [Server(f"MediaGW-{i}") for i in range(1, INITIAL_GATEWAYS + 1)]

    scaler = Python("Scaler")

    # Le scaler surveille Redis (par ex. nombre de locks, TTLs, trafic) pour scaler
    scaler >> Edge(xlabel="MONITOR: locks / TTL / metrics", style="dashed", color="red") >> redis
    scaler >> Edge(xlabel="UPSCALE / DOWNSCALE", style="dashed", color="red") >> gateways[3]

# Fin du script