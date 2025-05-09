#!/bin/bash
# zero-downtime-update.sh - Vereinfachtes Skript ohne RCON-Befehle

# Konfiguration
MINECRAFT_RELEASE="minecraft-server"
NAMESPACE="default"

# Farben für Ausgabe
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting Zero-Downtime Minecraft Update...${NC}"

# 1. Sicherstellen, dass Server 0 läuft
echo -e "${YELLOW}Ensuring server 0 is running...${NC}"
kubectl scale statefulset ${MINECRAFT_RELEASE} --replicas=1
kubectl wait --for=condition=ready pod/${MINECRAFT_RELEASE}-0 --timeout=180s

if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to ensure server 0 is running. Aborting.${NC}"
    exit 1
fi

# 2. Konfiguration aktualisieren
echo -e "${YELLOW}Updating Minecraft configuration...${NC}"
helm upgrade ${MINECRAFT_RELEASE} ./minecraft/ --set replicaCount=1

# 3. Weltdaten von Server 0 zu Backup synchronisieren
echo -e "${YELLOW}Syncing world data from server 0 to backup...${NC}"
kubectl exec -i ${MINECRAFT_RELEASE}-0 -- /bin/bash -c "/scripts/world-sync.sh to-backup"

# 4. Starte Server 1 mit den Backup-Weltdaten
echo -e "${YELLOW}Starting server 1 with backup world data...${NC}"
kubectl scale statefulset ${MINECRAFT_RELEASE} --replicas=2
kubectl wait --for=condition=ready pod/${MINECRAFT_RELEASE}-1 --timeout=180s

# 5. Lade Weltdaten aus dem Backup auf Server 1
echo -e "${YELLOW}Loading world data to server 1 from backup...${NC}"
kubectl exec -i ${MINECRAFT_RELEASE}-1 -- /bin/bash -c "/scripts/world-sync.sh from-backup"
sleep 10  # Warte, bis die Kopie abgeschlossen ist

# 6. Server 0 neustarten
echo -e "${YELLOW}Stopping server 0 for update...${NC}"
kubectl delete pod ${MINECRAFT_RELEASE}-0
kubectl wait --for=condition=ready pod/${MINECRAFT_RELEASE}-0 --timeout=180s

# 7. Weltdaten vom Backup zu Server 0 zurück synchronisieren
echo -e "${YELLOW}Syncing world data from backup to server 0...${NC}"
kubectl exec -i ${MINECRAFT_RELEASE}-0 -- /bin/bash -c "/scripts/world-sync.sh from-backup"

# 8. Server 1 herunterfahren
echo -e "${YELLOW}Shutting down server 1...${NC}"
kubectl scale statefulset ${MINECRAFT_RELEASE} --replicas=1

echo -e "${GREEN}Zero-Downtime Update completed successfully!${NC}"