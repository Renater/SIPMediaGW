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
    "labelfloat": "false"
}

with Diagram("MediaGW proxy ", show=False, filename="proxy", outformat="png", direction="LR", graph_attr=graph_attr):
    user = User("Web User")
    redis = Redis("Redis")
    proxy = Python("Proxy API")


    with Cluster("MediaGW Gateway Pool"):
        gateways = [Server(f"MediaGW-{i}") for i in range(1, INITIAL_GATEWAYS + 1)]



    # Flux principal : utilisateur -> proxy -> mediaGW
    user >> Edge(label="/start_record\n/stop_record") >> proxy

    # Le proxy sélectionne une gateway dans le pool et démarre l'enregistrement
    # Ici on représente la sélection en pointant sur la première gateway (conceptuel).
    proxy >> Edge(xlabel="select MediaGW\nstart\nstop") >> gateways[1]


    # Le proxy verrouille la gateway sélectionnée dans Redis (ex : SET lock:MediaGW-1)
    proxy >> Edge(label="lock MediaGW-1\nunlock MediaGW-1") >> redis

# Fin du script