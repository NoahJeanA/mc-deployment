#!/bin/bash
# zero-downtime-update.sh - Skript für Zero-Downtime-Updates mit BungeeCord

# Konfiguration
MINECRAFT_RELEASE="minecraft-server"
BUNGEE_RELEASE="bungee"
NAMESPACE="default"

# Farben für Ausgabe
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting Zero-Downtime Minecraft Update...${NC}"

# 1. Sicherstellen, dass beide Server-Instanzen laufen
echo -e "${YELLOW}Ensuring both Minecraft server instances are running...${NC}"
kubectl scale statefulset ${MINECRAFT_RELEASE} --replicas=2
kubectl wait --for=condition=ready pod/${MINECRAFT_RELEASE}-0 pod/${MINECRAFT_RELEASE}-1 --timeout=300s

if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to ensure both servers are running. Aborting.${NC}"
    exit 1
fi

# 2. Konfiguration aktualisieren (wird später wirksam)
echo -e "${YELLOW}Updating Minecraft configuration...${NC}"
helm upgrade ${MINECRAFT_RELEASE} ./minecraft/ --set replicaCount=2

# 3. Prüfen, ob Spieler verbunden sind
echo -e "${YELLOW}Checking for connected players...${NC}"
PLAYERS=$(kubectl exec -it ${MINECRAFT_RELEASE}-0 -- /bin/bash -c "cd /app && java -cp server.jar org.bukkit.craftbukkit.Main list | grep 'players online'")
echo -e "Player status: ${GREEN}${PLAYERS}${NC}"

# 4. Benachrichtigung an Spieler senden
echo -e "${YELLOW}Notifying players about server update...${NC}"
kubectl exec -it deployment/${BUNGEE_RELEASE} -- rcon-cli alert "Server-Update wird vorbereitet. Ihr werdet automatisch zum anderen Server umgeleitet."

# 5. Spieler zum Server 2 umleiten
echo -e "${YELLOW}Redirecting players to server2...${NC}"
kubectl exec -it deployment/${BUNGEE_RELEASE} -- rcon-cli send all server2
sleep 5

# 6. Server 1 neustarten
echo -e "${YELLOW}Restarting minecraft-server-0 with new configuration...${NC}"
kubectl delete pod ${MINECRAFT_RELEASE}-0
kubectl wait --for=condition=ready pod/${MINECRAFT_RELEASE}-0 --timeout=180s

# 7. Spieler zurück zu Server 1 umleiten
echo -e "${YELLOW}Redirecting players back to server1...${NC}"
kubectl exec -it deployment/${BUNGEE_RELEASE} -- rcon-cli alert "Update abgeschlossen. Ihr werdet zum aktualisierten Server zurückgeleitet."
kubectl exec -it deployment/${BUNGEE_RELEASE} -- rcon-cli send all server1
sleep 5

# 8. Server 2 neustarten
echo -e "${YELLOW}Restarting minecraft-server-1 with new configuration...${NC}"
kubectl delete pod ${MINECRAFT_RELEASE}-1
kubectl wait --for=condition=ready pod/${MINECRAFT_RELEASE}-1 --timeout=180s

echo -e "${GREEN}Zero-Downtime Update completed successfully!${NC}"