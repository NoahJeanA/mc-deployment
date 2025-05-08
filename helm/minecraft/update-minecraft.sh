#!/bin/bash
# update-minecraft.sh - Skript für Rolling Updates des Minecraft-Servers

# Konfiguration
RELEASE_NAME="minecraft-server"  # Hier Ihren Release-Namen eintragen
NAMESPACE="default"

# Farben für Ausgabe
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting Minecraft Server Rolling Update...${NC}"

# 1. Aktuelle Replikaanzahl ermitteln
CURRENT_REPLICAS=$(kubectl get statefulset ${RELEASE_NAME} -n ${NAMESPACE} -o jsonpath='{.spec.replicas}')
echo -e "Current replica count: ${GREEN}${CURRENT_REPLICAS}${NC}"

# Wenn Server ausgeschaltet ist (0 Repliken), einfach nur die Konfiguration aktualisieren
if [ "$CURRENT_REPLICAS" -eq "0" ]; then
    echo -e "${YELLOW}Server is currently scaled down to 0. Updating configuration only...${NC}"
    helm upgrade ${RELEASE_NAME} ../minecraft/ --set replicaCount=0
    echo -e "${GREEN}Configuration updated. Server remains scaled down.${NC}"
    exit 0
fi

# 2. Auf mindestens 2 Repliken hochskalieren, um ein Rolling Update zu erzwingen
echo -e "${YELLOW}Scaling to 2 replicas to initiate rolling update...${NC}"
helm upgrade ${RELEASE_NAME} ../minecraft/ --set replicaCount=2

# 3. Warten, bis der zweite Pod bereit ist
echo -e "${YELLOW}Waiting for new pod to be ready...${NC}"
POD_NAME="${RELEASE_NAME}-1"
kubectl wait --for=condition=ready pod/${POD_NAME} -n ${NAMESPACE} --timeout=300s

if [ $? -ne 0 ]; then
    echo -e "${RED}New pod failed to become ready within timeout. Rolling back...${NC}"
    helm upgrade ${RELEASE_NAME} ../minecraft/ --set replicaCount=${CURRENT_REPLICAS}
    exit 1
fi

echo -e "${GREEN}New pod ${POD_NAME} is ready!${NC}"

# 4. Warten, bis der neue Pod den Server vollständig gestartet hat (Optional)
echo -e "${YELLOW}Waiting for Minecraft server to initialize in new pod...${NC}"
ATTEMPTS=0
MAX_ATTEMPTS=30
while [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
    if kubectl logs ${POD_NAME} -n ${NAMESPACE} | grep -q "Done"; then
        echo -e "${GREEN}Minecraft server initialized successfully in new pod!${NC}"
        break
    fi
    ATTEMPTS=$((ATTEMPTS+1))
    echo -n "."
    sleep 10
done

if [ $ATTEMPTS -ge $MAX_ATTEMPTS ]; then
    echo -e "${YELLOW}\nWarning: Could not confirm Minecraft server initialization in new pod within timeout.${NC}"
    echo -e "${YELLOW}Continuing anyway...${NC}"
fi

# 5. Zurück auf die ursprüngliche Replikaanzahl skalieren (in der Regel 1)
echo -e "${YELLOW}Scaling back to ${CURRENT_REPLICAS} replica(s)...${NC}"
helm upgrade ${RELEASE_NAME} ../minecraft/ --set replicaCount=${CURRENT_REPLICAS}

# 6. Warten, bis die überflüssigen Pods terminiert sind
echo -e "${YELLOW}Waiting for excess pods to terminate...${NC}"
sleep 30

# 7. Fertig!
echo -e "${GREEN}Rolling update completed successfully!${NC}"
echo -e "${GREEN}Your Minecraft server has been updated with the new configuration.${NC}"

# Zeige Status der Pods
echo -e "${YELLOW}Current pod status:${NC}"
kubectl get pods -l app=${RELEASE_NAME} -n ${NAMESPACE}