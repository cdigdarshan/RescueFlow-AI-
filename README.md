# 🚦 RescueFlow AI: Real-Time Intelligent Traffic Management & Emergency Vehicle Priority System

An advanced, real-time computer vision and traffic management platform engineered to automate vehicle detection, track traffic density across lanes, and dynamically prioritize emergency vehicles (such as ambulances) to reduce transit delays at intersections.

---

## 🏗️ System Architecture

```text
[ Live Video Feed / Stream ]
             │
             ▼
   [ YOLOv8 Object Detection ] ──> (Classifies Vehicles & Ambulances)
             │
             ▼
   [ ByteTrack Multi-Object Tracker ] ──> (Maintains Trajectories & IDs)
             │
             ▼
   [ Lane-Wise Counting & Density Estimator ] 
             │
             ├──────────────────────────┐
             ▼                          ▼
   [ Adaptive Priority Logic ]   [ Flask Real-Time Web Dashboard ]
   (Emergency Routing Control)   (Interactive UI & Analytics)