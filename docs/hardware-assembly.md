# Hardware Assembly Guide

This guide covers the physical assembly of your Raspberry Pi Kubernetes cluster.

## Bill of Materials

### Core Components

| Component | Quantity | Notes |
|-----------|----------|-------|
| Raspberry Pi 5 (8GB) | 4 | Worker nodes |
| Ubuntu Desktop PC | 1 | Control plane |
| MicroSD Card (32GB+) | 4 | Boot drives for RPi |
| USB SSD (256GB+) | 4 | Storage for workers |
| 27W USB-C Power Supply | 4 | Official RPi5 PSU |
| Gigabit Ethernet Switch | 1 | 5+ ports |
| Cat6 Ethernet Cables | 5 | 0.5m - 1m length |

### Recommended Accessories

| Component | Quantity | Notes |
|-----------|----------|-------|
| Cluster Case/Rack | 1 | Acrylic stack or 3D printed |
| Active Cooler | 4 | Fan + heatsink for RPi5 |
| USB-C Cables | 4 | If using shared PSU |
| PoE+ HAT | 4 | Optional: Power over Ethernet |
| PoE+ Switch | 1 | If using PoE HATs |
| UPS | 1 | Recommended for production |

## Assembly Steps

### Step 1: Prepare Cooling

The Raspberry Pi 5 generates more heat than previous models. Active cooling is **strongly recommended**.

**Option A: Official Active Cooler**
1. Remove the thermal pad backing
2. Align cooler over the SoC
3. Press firmly until clips engage
4. Connect fan to the FAN header

**Option B: Third-Party Heatsink + Fan**
1. Apply thermal paste to SoC
2. Mount heatsink
3. Attach fan to GPIO pins 4 (5V) and 6 (GND)

### Step 2: Prepare Storage

**SD Card (Boot)**
1. Flash Raspberry Pi OS Lite (64-bit)
2. Enable SSH in Imager settings
3. Set hostname and credentials
4. Insert into RPi slot

**USB SSD (Data)**
1. Connect USB SSD to USB 3.0 port (blue)
2. The bootstrap scripts will format and mount automatically
3. Do NOT pre-format the drive

### Step 3: Assemble the Stack

**Cluster Case Assembly**
```
┌─────────────────────────┐
│     Ethernet Switch     │  ← Top
├─────────────────────────┤
│     RPi5 Node 4        │
├─────────────────────────┤
│     RPi5 Node 3        │
├─────────────────────────┤
│     RPi5 Node 2        │
├─────────────────────────┤
│     RPi5 Node 1        │  ← Bottom
└─────────────────────────┘
```

1. Stack RPi units with spacers (20-25mm recommended)
2. Ensure adequate airflow between units
3. Route cables neatly
4. Mount switch at top or side

### Step 4: Network Cabling

```
Router ──────┬──────────────── Desktop (Control Plane)
             │
             └──── Switch ─┬── RPi5 Node 1
                           ├── RPi5 Node 2
                           ├── RPi5 Node 3
                           └── RPi5 Node 4
```

1. Connect switch to router/main network
2. Connect each RPi to switch using short cables
3. Connect Ubuntu desktop to switch or router
4. Label cables for easy identification

### Step 5: Power Distribution

**Standard Setup (Individual PSUs)**
- Each RPi gets its own 27W USB-C PSU
- Use a power strip with surge protection
- Total power consumption: ~80W max

**PoE Setup (Power over Ethernet)**
- Install PoE+ HAT on each RPi
- Use PoE+ capable switch (802.3at)
- Simplifies cabling significantly
- Total PoE budget needed: ~60W

## Cable Management

### Recommended Layout

```
┌─────────────────────────────────────────────┐
│                                             │
│   ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐       │
│   │ PSU │  │ PSU │  │ PSU │  │ PSU │       │
│   └──┬──┘  └──┬──┘  └──┬──┘  └──┬──┘       │
│      │        │        │        │           │
│   ┌──▼──┐  ┌──▼──┐  ┌──▼──┐  ┌──▼──┐       │
│   │RPi 1│  │RPi 2│  │RPi 3│  │RPi 4│       │
│   └──┬──┘  └──┬──┘  └──┬──┘  └──┬──┘       │
│      │        │        │        │           │
│   ┌──▼────────▼────────▼────────▼──┐       │
│   │         Ethernet Switch         │       │
│   └────────────────┬────────────────┘       │
│                    │                         │
│                    ▼                         │
│               To Router                      │
└─────────────────────────────────────────────┘
```

### Tips

1. Use velcro straps for bundling cables
2. Leave slack for maintenance access
3. Keep power cables separate from data cables
4. Label everything!

## Thermal Considerations

### Airflow Design

```
        ↑ Hot Air Out ↑
    ┌───────────────────┐
    │    Exhaust Fan    │  (optional)
    ├───────────────────┤
    │                   │
    │    RPi Stack      │
    │    (spaced)       │
    │                   │
    ├───────────────────┤
    │    Intake Fan     │  (optional)
    └───────────────────┘
        ↑ Cool Air In ↑
```

### Temperature Targets

| Condition | Temperature | Action |
|-----------|-------------|--------|
| Idle | < 45°C | Normal |
| Light Load | 45-55°C | Normal |
| Heavy Load | 55-70°C | Normal |
| Throttling | 70-80°C | Improve cooling |
| Danger | > 80°C | Shutdown and fix |

### Monitoring

The cluster automatically monitors temperatures:
- View in Grafana dashboard
- Alert at 75°C
- Hardware throttling at 80°C
- Check with: `vcgencmd measure_temp`

## Physical Security

### Recommendations

1. **Location**: Place in a secure, ventilated area
2. **Access Control**: Limit physical access
3. **Backup**: Keep spare SD cards with OS images
4. **Documentation**: Label all components
5. **Photos**: Take photos of cable routing

### Disaster Recovery

Keep these items ready:
- Spare Raspberry Pi
- Pre-imaged SD cards
- Backup of `/etc/rancher/k3s/` from control plane
- Exported Kubernetes secrets

## Power Failure Protection

### UPS Recommendations

For a 5-node cluster:
- Minimum capacity: 300VA / 180W
- Runtime target: 10-15 minutes
- Features: USB monitoring, auto-shutdown

### Graceful Shutdown Script

```bash
#!/bin/bash
# /usr/local/bin/graceful-shutdown.sh

# Drain k3s nodes
for node in rpi5-node-{1..4}; do
    kubectl drain $node --ignore-daemonsets --delete-emptydir-data
done

# Shutdown workers
for i in {101..104}; do
    ssh pi@192.168.1.$i "sudo shutdown -h now"
done

# Wait for workers to stop
sleep 30

# Stop control plane k3s
sudo systemctl stop k3s

# Shutdown control plane
sudo shutdown -h now
```

## Expansion

### Adding More Nodes

1. Prepare new RPi with OS and cooling
2. Connect to network switch
3. Add to Ansible inventory
4. Run bootstrap playbook
5. Run k3s agent installation
6. Verify node joined cluster

### Storage Expansion

Options:
1. Larger USB SSDs
2. Network Attached Storage (NAS)
3. Distributed storage (Longhorn)
4. Cloud storage integration

## Troubleshooting

### No Network Connectivity

1. Check cable connections
2. Verify switch port LEDs
3. Check router DHCP
4. Test with `ping`

### No Boot

1. Re-flash SD card
2. Try different SD card
3. Check power supply
4. Verify cooling (thermal shutdown?)

### High Temperatures

1. Verify fans are running
2. Check thermal paste application
3. Improve case ventilation
4. Reduce workload

### USB SSD Not Detected

1. Try different USB port
2. Check drive health with `smartctl`
3. Try different SSD
4. Check power delivery (some SSDs need more power)
