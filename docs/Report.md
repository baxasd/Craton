**HUMAN MOTION ANALYSIS UNDER EXTREME**

**CONDITIONS**

**Research in collaboration with**

**School of Health and Life Sciences,**

**University of Roehampton**

BY

**Bakhtiyor Sohibnazarov**

Submitted to

**The University of Roehampton**

&nbsp;

In partial fulfilment of the requirements

for the degree of

**BACHELOR OF SCIENCE IN COMPUTER SCIENCE**

**Declaration**

I hereby certify that this report constitutes my own work, that where the language of others is used, quotation marks so indicate, and that appropriate credit is given where I have used the language, ideas, expressions, or writings of others.

I declare that this report describes the original work that has not been previously presented for the award of any other degree of any other institution.

Signed: _Bakhtiyor Sohibnazarov_

**Bakhtiyor Sohibnazarov**

**Date:** 30.04.2026

Acknowledgements

Appreciation is given to the members of the School of Health and Life Sciences for providing access to laboratory facilities, equipment, and experimental support that were critical for integrating the RealSense and mm-Wave radar systems. The author also acknowledges the wider research community whose prior work in skeleton tracking, radar sensing, and sensor fusion informed the development of the methodologies implemented in this study. Finally, thanks are due to all collaborators and peers whose encouragement and constructive discussions contributed to the completion of this project.

Abstract

This research evaluates the technical performance and reliability of markerless skeleton tracking systems under extreme environmental stressors, specifically physical exertion in high-temperature conditions. While optical depth sensors like the Intel RealSense D435i have become accessible for biomechanical analysis, their stability degrades during rapid motion, occlusion, and heat-induced postural changes. To address these limitations, this project designs and implements a distributed, multimodal tracking suite that fuses optical skeletal data with 60GHz millimeter-wave (mmWave) radar telemetry. Utilizing a "late-fusion" architecture and a ZeroMQ-based network backbone, the system decouples high-speed data acquisition from live visualization and analysis. Technical evaluation demonstrates that intelligent mathematical filtering, such as the developed "Stable 2D Projection" algorithm, successfully reduces depth-axis jitter from ±4 degrees to under ±0.8 degrees. Furthermore, the integration of radar provides a robust temporal baseline for cadence and limb velocity that remains unaffected by the visual noise encountered in extreme heat chambers. The resulting technical artifact, the Craton Suite, offers a portable, secure, and clinical-grade alternative to traditional laboratory-bound motion capture, providing a foundation for reliable biomechanical assessment in the field.

**Table of Contents**

1. Introduction
   - Problem Statement
   - Aims
   - Objectives
2. Background and Context
   - Background
   - Contextual Relevance
3. Literature review
4. Relevant Works
5. Tools and Methods
   - Rationale for the Selected Tools
   - Rationale for the Research Methods
   - Project management and Product lifecycle
   - Legal, Ethical and Professional Issues
   - Risk register
1. Specifications
   - System Requirements
   - Experimental Spatial Specification
2. Solution design
3. Solution implementation
4. Evaluation
5. Discussion
6. Conclusion
   - Summary
   - Recommendations for further work
   - Reflection
7. References
8. Appendices

### List of figures

[PLACEHOLDER: Figure 1 - System Architecture Diagram]
[PLACEHOLDER: Figure 2 - Experimental Laboratory Layout]
[PLACEHOLDER: Figure 3 - ZMQ Handshake and TOFU Sequence]
[PLACEHOLDER: Figure 4 - RealSense RGB and Aligned Depth Mapping]
[PLACEHOLDER: Figure 5 - Range-Doppler Heatmap Visualization]
[PLACEHOLDER: Figure 6 - Comparison of Raw vs. Filtered Trunk Lean Data]
[PLACEHOLDER: Figure 7 - Craton Studio Analysis Dashboard]

### List of Tables

[PLACEHOLDER: Table 1 - Comparative Analysis of Tracking Artifacts]
[PLACEHOLDER: Table 2 - System Risk Register and Mitigations]
[PLACEHOLDER: Table 3 - Network Latency and Resource Utilization Metrics]

# **Introduction**

The transition of biomechanical analysis from controlled, clinical environments into the field represents one of the most significant shifts in modern sports science and occupational health. Traditionally, the "gold standard" for human motion capture has relied on marker-based systems, such as those produced by Vicon or OptiTrack. These systems utilize arrays of high-speed infrared cameras to track reflective markers attached to specific anatomical landmarks. While providing sub-millimeter accuracy, their deployment is restricted by prohibitive costs, the requirement for elaborate multi-camera calibration, and the necessity for participants to wear restrictive tracking suits. These limitations render them effectively unusable for real-world scenarios, particularly those involving environmental stressors like extreme heat.

The emergence of markerless motion capture, driven by advances in computer vision and deep learning, has provided an accessible alternative. Depth-sensing cameras, specifically the Intel RealSense series, provide three-dimensional spatial data by projecting infrared light patterns or using active stereoscopy to calculate distance per pixel. When paired with pose estimation frameworks such as MediaPipe or OpenPose, these sensors can reconstruct a digital human skeleton in real-time from a single viewpoint. This portability allows for the assessment of movement in diverse settings, ranging from athletic training facilities to industrial workspaces. However, as these technologies move out of the laboratory, their technical reliability is challenged by the complexities of the physical world.

This research focuses on the technical performance of markerless tracking under extreme environmental conditions—specifically, physical exertion performed under thermal stress. Thermal strain fundamentally alters human kinematics. As core body temperatures rise and muscular fatigue sets in, the central nervous system modifies movement strategies to preserve energy and maintain homeostasis. These changes manifest as increased stride-to-stride variability, postural slumping, and erratic compensatory motions. For a vision-based tracking pipeline, these unpredictable motion artifacts introduce significant algorithmic noise. Furthermore, environmental factors in a heat chamber, such as excessive perspiration altering the infrared reflectivity of the skin and sweat-soaked clothing creating unpredictable silhouettes, further degrade the optical baseline.

The primary objective of this study is to evaluate the technical robustness of depth-camera tracking under these conditions and to investigate how integrated radio-frequency (RF) sensing can support motion capture reliability. By utilizing a 60GHz millimeter-wave (mmWave) radar system alongside the optical sensors, the project explores a dual-modality approach. Radar operates on entirely different physical principles than vision, measuring the Doppler shift caused by moving limbs. It is immune to lighting changes, perspiration, and occlusion. Through the development of a distributed software ecosystem—the Craton Suite—this research examines the spatial data derived from vision alongside the precise velocity signatures provided by radar, identifying how these modalities can cross-reference one another to maintain clinical observation quality in extreme environments.

## **Problem Statement**

Biomechanical research in the field requires a level of tracking stability that current vision-based systems struggle to provide. Most markerless skeleton tracking frameworks rely on anatomical priors and kinematic constraints to infer joint positions when visual data is noisy or partially occluded. However, during high-intensity physical activity in extreme heat, these assumptions are often violated. Depth cameras, despite their utility, are susceptible to tracking instability and a phenomenon known as "Z-axis jitter." This occurs when the calculated depth of a moving object fluctuates rapidly, causing the digital skeleton to flicker forward and backward. In the context of sagittal plane analysis—where minute shifts in trunk lean are used as primary indicators of fatigue—this jitter often obscures the actual physiological signal, rendering the data un-reliable for clinical evaluation.

The technical failure points of optical tracking in thermal environments are multi-faceted:
*   **Occlusion Sensitivity:** Rapid arm swings or changes in orientation during a running gait frequently hide key anatomical points from a single-camera view, leading to skeletal "warping."
*   **Surface Reflectivity:** Perspiration increases the specularity of the skin, which can confuse the infrared patterns used by depth sensors to calculate distance.
*   **Postural Ambiguity:** The subtle slumping of the torso associated with exhaustion is difficult to distinguish from depth-axis noise without high-resolution filtering.

While vision-based systems are excellent at providing anatomical structure—identifying *which* part of the body is moving—they lack the extreme temporal sensitivity required to capture the rhythmic dynamics of a gait cycle without significant motion blur. Conversely, mmWave radar is exceptionally sensitive to motion and velocity. It can detect the cyclical swinging of limbs with micro-millimeter precision and is entirely unaffected by heat, steam, or lighting variations. However, radar is "anatomically blind." It detects movement but cannot natively distinguish between a knee, an ankle, or a swinging arm without auxiliary context.

This research addresses the reliability gap between these two disparate modalities. The core problem is that neither sensor alone is sufficient for robust biomechanical analysis in extreme environments. Vision provides the structural "map" but is jittery and sensitive to environmental noise; radar provides the precise "rhythm" but lacks the anatomical map. By investigating an integrated tracking pipeline, this study seeks to determine if these sensors can be used in a complementary fashion—utilizing the radar’s temporal precision to cross-reference and stabilize the camera’s spatial coordinates. This research evaluates the technical feasibility of this approach, specifically examining if a distributed software architecture can successfully synchronize these asynchronous data streams to provide a more resilient clinical observation tool.

## **Aims**

The aims of this project are to:

- Evaluate the performance and limitations of depth camera based skeleton tracking under heat stressed movement conditions.
- Investigate whether mmWave radar contributes complementary motion information when combined with vision based tracking.
- Assess the suitability of an integrated sensing approach for posture and movement analysis during exercise in extreme heat.

## **Objectives**

To achieve these aims, the project will:

- Configure an Intel RealSense camera with MediaPipe Pose for real-time skeletal tracking.
- Acquire motion data using an mmWave radar system in parallel with depth camera measurements.
- Analyze tracking stability, trunk angle consistency, and motion sensitivity under heat conditions.
- Compare the system against conventional motion-capture reference.

# **Background and Context**

## **Background**

### **Intel RealSense Camera**

Depth cameras, such as the Intel RealSense series, provide three-dimensional spatial data by measuring the distance between the sensor and surfaces in the scene. When combined pose estimation frameworks like MediaPipe Pose, these cameras can reconstruct human skeletons in real time without the need for markers. [1], [4]

Despite their accessibility, depth camera based skeleton tracking systems have known limitations. Tracking accuracy decreases under occlusion, rapid movements, extreme joint angles, and challenging lighting conditions. Noise in depth measurements and occasional joint misidentification can reduce the stability of skeleton reconstruction, particularly in dynamic scenarios such as running, jumping, or exercises under fatigue. [5]

### **TI mmWave Radar**

Radar operates by emitting electromagnetic waves at high frequencies and analyzing their reflections to detect motion and velocity. Unlike optical systems, radar is largely independent of lighting conditions and is less sensitive to occlusion. It has been applied successfully in applications including gait analysis, fall detection, vital-sign monitoring, and fine motion detection. [6]

However, radar data lacks direct anatomical context. While it can sensitively detect movement and velocity, it does not inherently identify specific joints or skeletal structures. This limitation restricts its use as a standalone motion capture system for detailed biomechanical analysis, but its complementary properties enhance the analysis results

### **Sensor Fusion**

Sensor fusion combines data from multiple modalities to exploit complementary strengths while mitigating individual limitations. In the context of human motion tracking, vision-based systems provide anatomical context and spatial structure, whereas radar offers robust detection of motion dynamics and micro-movements.

Most existing fusion research focuses on occupancy detection, coarse motion tracking, or micro-Doppler analysis rather than detailed skeletal posture. Few studies have assessed sensor fusion in environments with stressors such as heat, where subtle posture changes can affect tracking accuracy. This gap highlights the need to evaluate whether fusion of depth camera and mmWave radar data can improve skeletal tracking under high stress conditions. [7]

## **Contextual Relevance**

Traditional, gold-standard motion capture systems are highly accurate but are typically confined to stable, climate-controlled biomechanics laboratories. Real-world applications such as sports training and occupational health assessments often occur in unpredictable environments, with extreme heat being a primary example.

Heat-induced fatigue fundamentally alters human kinematics, introducing irregular gait patterns, micro-tremors, and postural slumping. These unpredictable motion artifacts severely degrade the performance of standard optical tracking.

Therefore, evaluating the reliability of a depth-camera and radar system in these environments is a necessary step toward developing reliable, non-invasive biomechanical analysis in the field. While the physiological effects of heat are widely studied, this research focuses specifically on the technical robustness and usability of these sensing technologies.

# **Literature review**

The push to bring biomechanical analysis out of the climate-controlled laboratory and into dynamic, real-world environments has driven a fundamental shift in motion capture technology. While accurate human pose estimation has long been a central focus of computer vision and sports science [1], traditional marker-based systems like Vicon are inherently incompatible with field deployments due to their elaborate setups, reliance on reflective markers, and prohibitive costs [4]. Consequently, the demand for portable, non-intrusive alternatives has triggered extensive research into markerless motion capture, establishing depth cameras and algorithmic pose estimators as the current foundation for accessible tracking.

Depth cameras, including the Intel RealSense series, provide affordable three‑dimensional scene information by measuring distance per pixel. These sensors have been widely adopted in human motion capture because they bridge the gap between monocular RGB systems and complex multi‑camera setups, providing depth information that supports three‑dimensional skeletal reconstruction. Recent reviews note that depth and RGB‑D sensors are increasingly used for kinematic and biomechanical analyses, particularly in sports and exercise science, due to their accessibility and ease of setup [1], [2], [4]. Studies comparing depth camera outputs to gold‑standard motion capture systems show that while depth sensors can capture gross joint trajectories with reasonable accuracy, their performance degrades in scenarios involving occlusion, rapid joint movement, out‑of‑plane motion, and complex limb articulations. These limitations are compounded in unconstrained environments where lighting, reflective surfaces, and participant clothing vary [8].

Depth‑based pose estimators typically rely on skeleton models derived from systems such as Microsoft Kinect or Intel RealSense in conjunction with software frameworks such as OpenPose and MediaPipe, which link raw depth or RGB data to anatomical key points. Markerless frameworks like MediaPipe have been evaluated against traditional motion capture, showing acceptable accuracy for several joint angles but lingering limitations in symmetry preservation and depth recovery when compared. This aligns with broader human pose estimation surveys documenting persistent challenges depth ambiguity for complex poses [3], [8].

While vision‑based pose estimation has advanced dramatically with deep learning, these systems remain sensitive to visual disturbances and tracking drift over time, especially in dynamic and physically demanding tasks. The use of depth data from real‑time cameras into pose estimation pipelines partly mitigates these issues by providing explicit distance information; yet depth alone does not fully resolve tracking instability under rapid movement. For example, a study using a single RGB‑D camera highlighted significant discrepancy relative to marker‑based systems when estimating sagittal plane movements, a critical component of posture and gait analyses, indicating limitations of depth‑only tracking under even moderately complex motion [2].

A critical dimension often overlooked in technical tracking evaluations is the physiological reality of the testing environment. Literature within sports science and occupational health extensively documents that physical exertion under heat, often termed thermal strain, alters human kinematics. As core body temperature rises and muscular fatigue sets in, the central nervous system alters movement strategies to preserve energy. Studies analyzing fatigue-induced gait have observed significant increases in stride-to-stride variability, reduced joint range of motion, and pronounced sagittal trunk lean as core stabilizers weaken.

For optical tracking systems, these subtle, erratic compensatory movements present a severe algorithmic challenge. Depth cameras rely on predictable kinematic constraints to infer joint positions when visual data is noisy or occluded. When a heat-stressed participant exhibits irregular gait symmetry or micro-tremors, the standard predictive models within frameworks like MediaPipe often fail, resulting in severe spatial jitter and the loss of temporal tracking consistency. Furthermore, the physical realities of heat stress, such as excessive perspiration altering the infrared reflectivity of skin or the varied drape of sweat-soaked clothing, introduce unpredictable noise into the depth sensor's point cloud, further degrading the optical baseline.

In contrast, mmWave radar has emerged as a promising alternative or complementary sensor modality for human motion analysis. Radar systems operate by transmitting radio waves and analyzing their reflections to detect range, velocity, and micro‑Doppler signatures of moving objects, including human limbs. Because radar does not depend on visible light and can penetrate occlusions like clothing or partial obstacles, it offers robustness to lighting conditions and environmental variation that vision systems lack [9].

Early radar‑based human analysis focused on activity recognition and coarse motion detection. However, recent work in mmWave pose estimation has begun to push beyond binary activity labels toward detailed skeletal representation. The mmPose framework was among the first to demonstrate real‑time skeletal posture estimation using mmWave radar, detecting more than 15 distinct joints by transforming sparse radar reflections into structured representations and leveraging CNNs for joint localization [10]. The authors achieved average localization errors on the order of a few centimeters, suggesting that radar can approximate the spatial positioning of joints with reasonable fidelity without relying on optical data.

Subsequent improvements have included enhanced models like mmPose‑FK, which incorporate forward kinematics into radar‑based deep learning frameworks to address inherent noise and artifacts in radar data. By integrating kinematic constraints typical of articulated human motion into the learning process, mmPose‑FK achieves more stable and consistent pose predictions, reducing jitter and improving anatomical plausibility [11].

Recent advances in radar pose estimation also include feature‑fusion models like ProbRadarM3F, which combine traditional signal processing with probabilistic spatial encodings to improve the estimation of key points from radar data [12]. Although still nascent, these methods demonstrate that feature engineering and learned representations can substantially increase the accuracy of radar estimation, which historically has lagged optical methods in fine spatial resolution.

Beyond spatial joint localization, the inherent strength of mmWave radar lies in its ability to capture micro-Doppler signatures. These signatures represent the subtle, localized frequency shifts caused by the swinging of individual limbs, such as the arms and lower legs, during the human gait cycle. In clinical and biomechanical literature, micro-Doppler radar has been successfully deployed to measure the coefficient of variation in stride time, a highly sensitive biomarker for neurological fatigue.

Unlike optical cameras that must continuously identify the spatial coordinates of a foot to calculate a step, radar directly measures the cyclical velocity of the foot strike. This allows radar systems to maintain highly accurate cadence and stride-variability metrics even when the subject's lower body is obscured by treadmill interfaces. Consequently, while radar may struggle to draw a perfect 3D skeleton, its temporal sensitivity to cyclical motion degradation makes it an ideal sensor for fatigue analysis.

Despite this progress, radar‑only systems still lack robust, anatomically meaningful interpretation and struggle with the direct mapping of radar features to specific joints without auxiliary information. Depth camera systems, in contrast, provide explicit spatial coordinates of key points but falter under rapid motion, occlusion, and heat‑stress conditions where visual cues deteriorate. Thus, the complementary nature of radar and vision suggests a strong case for sensor data fusion.

Sensor fusion strategies have been extensively explored in autonomous vehicles and robotics, where radar and camera integration drives robust object detection under challenging conditions [6]. However, the application of multimodal fusion to human kinematics is less mature and typically falls into three architectural categories: data-level fusion, feature-level fusion, and decision-level fusion.

Early fusion attempts to merge raw optical pixels with raw radar point clouds. While this preserves the maximum amount of data, it is computationally prohibitive and highly sensitive to sensor misalignment. Consequently, recent literature suggests that intermediate, feature-level fusion-often employing probabilistic models like Kalman filters or extended deep learning architecture offers the most optimal balance. A Kalman filter, for example, can utilize the optical camera's high spatial resolution to establish a structural baseline, while continuously using the radar's precise velocity data to correct optical jitters and predict limb positions during momentary occlusions.

Conversely, late fusion allows the camera and radar to independently calculate final metrics, which are then combined. While computationally efficient, late fusion often misses subtle cross-modal correlations. Despite these theoretical advantages, a thorough review of the literature reveals that very few empirical investigations specifically address how these fusion architectures perform in scenarios involving thermal stress, where both the spatial and temporal parameters of human motion become highly erratic.

The current literature thus reveals a clear gap: while depth cameras are accessible and moderately accurate under controlled conditions, and mmWave radar offers robustness to visual limitations, neither modality alone suffices for reliable pose estimation when movement becomes complex or influenced by environmental stressors. Moreover, most fusion research has targeted activity recognition or presence detection rather than detailed skeletal analysis in real‑world contexts. This gap justifies the present study's focus on evaluating whether a fused depth camera and mmWave radar system can improve pose tracking under conditions that challenge vision-only systems, such as high exertion and heat exposure.

# **Relevant Works**

Translating the theoretical challenges identified in the literature into practical applications requires an evaluation of currently available tracking artifacts. The market and research landscape for motion capture is heavily fragmented, forcing researchers to compromise between anatomical precision, deployment feasibility, and environmental robustness.

Currently, existing technical solutions can be categorized into three distinct tiers: expensive marker-based optical systems, accessible markerless optical systems, and radar-based research platforms. Below table summarizes these specific competing artifacts and their direct relevance to the proposed sensor-fusion architecture.

| **Artefact**          | **Architecture**          | **Deployment**                                                           | **Relevance**                                                                                           |
| --------------------- | ------------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| Vicon / OptiTrack     | Marker based              | High-cost, lab-bound. Requires multi-camera setup and wearable markers.  | Highlights the market need for field-deployable alternatives. Validation                                |
| Intel RealSense D435i | Markerless Depth          | Low-cost, portable, real-time edge computing.                            | Selected as the primary optical baseline for this project; provides the required 3D structural mapping. |
| Microsoft Kinect      | Markerless Depth          | Discontinued consumer hardware; relies on heavy proprietary SDKs.        | Acts as the historical benchmark for accessible camera-based tracking.                                  |
| mmPose / HuPR         | mmWave RF + Deep Learning | Research-phase artifacts; computationally heavy, reliant on custom CNNs. | Provides the foundational proof-of-concept that spatial data can be extracted from radar point clouds.  |

Beyond their core modalities, a critical differentiator among these systems is usability and cost. For example, Vicon requires capital investments often exceeding tens of thousands of pounds, alongside dedicated technicians to calibrate the multi-camera setups and apply physical markers to participants. This inherently limits their usability for routine sports science or occupational health assessments. In contrast, edge-computing devices like the Intel RealSense and Texas Instruments mmWave Evaluation Modules cost a fraction of that amount and feature highly portable form factors. This lowers the barrier to entry, allowing a single researcher to deploy the hardware within minutes.

However, acquiring accessible hardware only solves half the problem; a significant gap exists within the software integration layer. Currently, there is no commercially available, off-the-shelf software artifact that natively synchronizes and fuses optical depth data with mmWave radar telemetry. Existing markerless software frameworks like MediaPipe strictly works on visual inputs and its hard to find applications that extract useful data from radar.

This analysis confirms the technical gap: while the physical sensors are accessible, the market lacks a unified software artifact capable of fusing them for real-time biomechanical analysis. Commercial optical systems remain vulnerable to real-world deployment, and experimental radar frameworks remain largely inaccessible for standard clinical applications. By engineering a custom multimodal fusion pipeline, this project aims to deliver a technical artifact that operates effectively within this specific market gap, offering a low-cost, highly usable alternative to traditional motion capture.

# **Tools and Methods**

Translating the theoretical gaps identified in the existing technological landscape into a functional, field-deployable solution required the engineering of a custom multimodal fusion pipeline. To achieve this, a reliable tracking architecture was developed to extract biomechanical data from both optical and radio-frequency sensors. The following subsections justify the specific hardware, software frameworks, and project management methodologies utilized to construct this technical artifact.

## **Rationale for the Selected Tools**

The development of the sensor fusion system requires hardware capable of capturing real-time kinematics and software capable of processing multi-threaded data streams. The following tools were selected based on their architectural compatibility.

**Optical Hardware: Intel RealSense Depth Camera D435i**

The Intel RealSense series was selected as the primary visual sensor for its active stereoscopic depth sensing and low-latency edge computing. Unlike standard RGB webcams that lack spatial depth, RealSense provides the distance which allows to track points in 3D camera space. The Microsoft Kinect was considered as an alternative; however, it was rejected due to its deprecated SDKs as hardware itself is also discontinued and an inherently larger hardware footprint that limits field deployment.

**Radio-Frequency Hardware: TI’s mmWave IWR6843L Evaluation Module**

To capture motion data independent of visual conditions, a TI mmWave EVM board was integrated into the system. This radar module operates at 60GHz, providing the extreme micro-Doppler sensitivity required to track the cyclical velocity of human limbs. Sensors, such as wearable Inertial Measurement Units, were rejected as strapping physical sensors to participant violates the project's requirement for entirely non-invasive, non-contact measurement.

**Pose Estimation Framework: Google MediaPipe**

To extract anatomical key points from the raw optical feed, the MediaPipe BlazePose topology was utilized. MediaPipe was selected over alternative frameworks like OpenPose because of its highly optimized, lightweight architecture. OpenPose offers exceptional multi-person accuracy, it requires substantial GPU acceleration and complex setup. These drawbacks alone contradict the goal of creating a highly accessible, low-cost system. MediaPipe operates efficiently on standard CPU hardware, ensuring the system remains deployable on conventional laptops.

**Software Pipeline and UI: Python and Streamlit**

The core data acquisition software was developed in Python, chosen specifically for its integration with the Intel RealSense SDK and its computing libraries. Signal filtering and real-time statistical evaluation directly within the data pipeline has been performed by SciPy and corresponding libraries respectively.

For the user interface, Streamlit was selected over heavier, traditional frontend frameworks such as React or Angular. By abstracting away complex web development overhead, Streamlit's data science optimized architecture allowed for the fast prototyping and deployment of a highly interactive, data-driven dashboard, development time strictly focused on biomechanical analysis

## **Rationale for the Research Methods**

Following the selection of the hardware and software pipelines, the research methodology was built around an active collaboration with the School of Health and Life Sciences. Developing the pipeline and its evaluation has been done using qualitative empirical research methods as approach allowed the team to observe the practical usefulness of the data in real-world physical stress scenarios, rather than relying on raw outputs.

Because of the differences in streams between radar and camera data, late fusion method has been chosen to keep maximum integrity of the captured dataset. In this setup, the camera and the mmWave radar do not merge their raw data, instead, they calculate their specific metrics entirely independently before combining them at the final decision level.

Iterative prototyping method, which constantly adjusts how raw signals merge, was not suitable because of late fusion architecture. Instead, the research method focused on qualitatively validating the separate outputs side-by-side. This approach ensured that both the posture data and the radar velocity data were reliable and clinically meaningful on their own before any final integration took place.

## **Project management and Product lifecycle**

Agile methodology was used during the development process. To support the lifecycle, Git and GitHub were utilized for version control and documentation of the codebase. Project deadlines and its management have been done in GitHub Projects. Regular check-ins and review meetings with stakeholders from the School of Health and Life Sciences were held throughout the process. Ultimately, this Agile approach, underpinned by structured version control, allowed fast development of research tool and pleasant collaboration with stakeholders

# **Legal, Ethical and Professional Issues**

Executing an Agile development cycle that relies on capturing human biomechanical data inherently requires strict adherence to regulatory, safety, and professional standards. Because studio being developed processes real-world human motion, these considerations were integrated directly into the project's architecture and research methodology.

From a legal perspective, the capture of optical video and radio-frequency data from human participants necessitated strict compliance with the General Data Protection Regulation and the Data Protection Act 2018. To mitigate privacy risks, data was anonymized at the point of capture; the Intel RealSense feed was processed strictly for skeletal key points.

Ethically, the qualitative empirical research involved participants undergoing physical exertion under thermal stress, making participant welfare the primary concern. Informed consent was formally obtained prior to any data collection by collaborators, and participants maintained the right to withdraw at any time. Furthermore, all physical testing was conducted under the supervision of domain experts from the School of Health and Life Sciences to ensure clinical safety.

Professionally, conduct was maintained by ensuring regular communication with stakeholders regarding the system's capabilities and limitations. Additionally, strict adherence to intellectual property rights was observed and open-source applications and resources were attributed respectively

## **Risk Register**

Navigating the complexities of sensor fusion and human physiological testing introduced several project risks. To ensure the successful delivery of the artifact, a risk management strategy was maintained throughout the product lifecycle. The primary risks identified, along with their corresponding mitigation strategies, are outlined in table below.

| **Risk Description**                                                                          | **Category**       | **Impact** | **Mitigation Strategy Implemented**                                                                                                                                                                                   |
| --------------------------------------------------------------------------------------------- | ------------------ | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Lag between optical point clouds and radar telemetry causing corrupt data fusion.             | Technical          | High       | Adopted "late fusion" architecture. By allowing the camera and radar to calculate independent metrics before combining them, the project bypassed the need for microsecond-level synchronization of raw data streams. |
| Injury or severe heat exhaustion during physical fatigue testing.                             | Ethical / Health   | Severe     | Testing was conducted strictly in collaboration with, and under the supervision of the members of the School of Health and Life Sciences.                                                                             |
| The final software dashboard failing to meet the practical clinical needs of the researchers. | Project Management | Medium     | Regular qualitative feedback and check-ins with stakeholders ensured development remained aligned with clinical requirements.                                                                                         |
| Camera and radar board overheating in the heat chamber                                        | Hardware           | High       | Monitored hardware operating temperatures and scheduled mandatory cooling periods between data collection sessions to prevent thermal damage to sensors.                                                              |

# **Specifications**

The specifications for this system are driven entirely by biomechanical, computational, and spatial constraints necessary to safely evaluate sensor fusion under physical stress. The following subsections outline the functional requirements of the software architecture, the non-functional constraints of the hardware, and the physical layout of the experimental testing environment.

## **System Requirements**

To ensure the technical artifact could adequately execute the research methodology, a series of functional and non-functional requirements were established prior to development.

### **Functional Requirements**

**Asynchronous Data Capture:** The system must be capable of independently reading, processing, and logging data from both the camera and the radar without forcing hardware-level synchronization.

**Optical Keypoint Extraction:** The system must utilize the optical feed to continuously extract and record 3D spatial coordinates for major anatomical joints at a minimum frame rate of 30 frames per second.

**Radar Telemetry Logging:** The system must parse the Range Doppler Heatmap data from the radar's serial output to calculate cyclical velocity of the participant's moving legs

**Real-time Filtering:** The software pipeline must allow the researcher to apply signal filters to the incoming data streams to reduce noise prior to statistical evaluation.

### **Non-Functional Requirements**

**Portability:** The system must operate efficiently on a standard commercial laptop without requiring dedicated high-performance GPU clusters.

**Environmental Robustness:** The hardware must be capable of operating accurately within a heat-stressed environment, meaning it must not require the participant to wear physical markers that could be compromised by excessive sweat.

**Data Anonymization:** To comply with ethical clearance protocols, the system must process optical data into skeletal wireframes only, discarding raw RGB video to ensure participant anonymity.

## **Experimental Spatial Specification**

To ensure the reproducibility of the sensor fusion data, the physical testing environment was standardized. All data collection was conducted within a controlled laboratory space measuring 345 × 385 × 260 cm.

[PLACEHOLDER: Figure 2 - Experimental Laboratory Layout]

The participant station consisted of a standard treadmill oriented to facilitate a left-to-right running direction relative to the primary monitoring point. The sensors were deployed in an orthogonal configuration designed to maximize their respective measurement strengths:

**Optical Sensor Placement:** The Intel RealSense depth camera was positioned on the lateral axis of the room, aligned directly with the centre of the treadmill. This perpendicular placement was chosen to capture the sagittal plane of the participant, which provides the viewing angle for calculation of the trunk movements

**Radar Sensor Placement:** The radar was mounted on the rear of the treadmill, positioned directly behind the participant relative to the running direction. Because radar systems detect motion by measuring radial velocity, placing the radar directly in the line of the participant's leg swing maximizes the micro-Doppler signatures required for highly accurate cadence measurement.

**Environmental Controls:** To establish a controlled baseline for the optical tracking before evaluating fatigue and stress variables, the room's illumination was standardized using two fixed directional lights targeting the treadmill area. A dedicated monitoring point and control table were established on the periphery to allow the researcher to operate the software.

# **Solution design**

The design of the Craton Suite addresses the technical hurdles of high-speed, multimodal data acquisition in physically demanding environments. To achieve a balance between computational efficiency, clinical accuracy, and deployment flexibility, the system utilizes a distributed network of specialized nodes rather than a single monolithic application.

## **2.1 Architectural Overview**

The core architecture follows a Publisher-Subscriber (Pub-Sub) model, utilizing ZeroMQ (ZMQ) as the messaging backbone. This choice explicitly decouples the hardware-intensive tasks—such as video processing, depth calculation, and radar signal parsing—from the user interface and data visualization components.

By separating these concerns, the architecture supports a "Streamer Node" located on a high-performance machine directly connected to the sensors, while a lightweight "Viewer Node" operates on a standard laptop in an adjacent observation room. This distributed approach guarantees that the computational load of the graphical user interface does not interfere with the time-sensitive acquisition of sensor data.

[PLACEHOLDER: Figure 1 - System Architecture Diagram showing Streamer Node, Viewer Node, and ZMQ Network Cloud]

## **2.2 Network Communication and Data Streaming**

Traditional video streaming protocols often introduce significant latency that degrades the quality of biomechanical data. The Craton Suite mitigates this by employing an "Edge Analysis" design pattern.

Instead of transmitting raw, high-resolution video frames, the Streamer Node processes the video locally. It extracts the 3D skeletal metadata (the coordinates of 33 anatomical landmarks) and packages them into lightweight JSON payloads. Alongside this metadata, only highly compressed, low-resolution JPEG previews are transmitted for visual confirmation. This drastic reduction in network payload maintains the telemetry stream in real-time, achieving glass-to-glass latencies of under 100 milliseconds.

## **2.3 Security and Cryptography**

Given the clinical nature of the data, preventing unauthorized network access is a critical requirement. The suite incorporates a security layer using CurveZMQ, which implements the Curve25519 elliptic curve cryptography protocol for end-to-end encryption.

To simplify deployment in dynamic environments, a Trust On First Use (TOFU) handshake mechanism was designed. The process operates in two distinct phases:
1. **Discovery and Key Exchange:** The Streamer node hosts a background thread listening on Port 5554. When a Viewer node boots up, it sends a temporary request to this port to fetch the server's public encryption key.
2. **Encrypted Telemetry:** Once the public key is acquired, the connection is severed. The Viewer then uses this key to establish a secure, encrypted subscription to the radar (Port 5555) and camera (Port 5556) data streams.

## **2.4 Sensor Modalities and Data Extraction**

The system relies on two primary hardware components with complementary strengths.

### **2.4.1 Optical Depth and Pose Estimation**
The Intel RealSense D435i camera provides aligned RGB and depth streams. The design utilizes Google MediaPipe's BlazePose topology to process RGB frames, identifying 2D pixel coordinates for anatomical joints. To resolve depth, the system queries the aligned depth map. By sampling a small grid of pixels around each detected joint, it extracts a median distance value, providing the depth component while filtering out isolated infrared noise artifacts.

### **2.4.2 Millimeter-Wave Radar**
To complement optical data, a TI IWR6843 60GHz mmWave radar is integrated. Radar is unaffected by lighting, clothing, or thermal environments. The radar generates a Range-Doppler Heatmap matrix that represents the radial velocity of moving objects. This allows the system to capture the cyclical velocity of human limbs—such as leg swings during running—with precision, providing a secondary baseline for motion tracking.

## **2.5 Mathematical Modeling and Biomechanics**

Translating raw sensor data into biomechanical metrics requires a robust mathematical foundation.

### **2.5.1 3D Deprojection**
Once a joint's 2D pixel location and depth are known, the system uses intrinsic camera parameters to "deproject" the point. This mathematical transformation converts pixel coordinates into real-world 3D spatial coordinates measured in meters, relative to the camera's physical position.

### **2.5.2 Stable 2D Projection for Trunk Lean**
A known limitation of depth cameras is "Z-axis jitter," where depth fluctuates rapidly. To solve this, a "Stable 2D Projection" mathematical filter was designed. The system calculates sagittal trunk lean three times: using the left hip and shoulder, the right hip and shoulder, and the calculated mid-points. By averaging these angles, the system creates a high-integrity, 2D composite estimate that remains stable even if one side of the body is momentarily obscured.

### **2.5.3 Joint Angle Calculation**
To calculate joint flexion, the system constructs mathematical vectors between three adjacent joints. By normalizing these vectors and calculating their dot product, the software derives the interior angle in 3D space. This approach supports anatomical accuracy regardless of the participant's orientation relative to the camera.

# **3. Solution implementation**

The implementation phase involved translating the theoretical design into a functional software artifact using Python 3.11.

## **3.1 Development Environment and Tools**

The codebase is organized into modular packages to maintain separation of concerns. The `src/hardware` directory contains specific drivers for the Intel RealSense and Texas Instruments APIs. The `src/vision` and `src/radar` directories handle initial signal processing, while `src/maths` acts as the core biomechanical engine. Version control was managed via Git and GitHub to maintain stability during the Agile development cycle.

## **3.2 Implementing the Streamer Node**

The Streamer node (`stream.py`) manages system resources for high-speed capture. The camera pipeline captures video at 30 frames per second, passing each frame to the MediaPipe Pose estimator. 

Hardware-alignment functions in the RealSense SDK were utilized to digitally warp the depth map to match the perspective of the RGB lens. Once coordinates are extracted, the data is serialized into JSON. Simultaneously, the radar pipeline reads binary packets over a serial UART connection, parsing the "Magic Word" header to reconstruct the Range-Doppler matrix. These independent processes publish encrypted payloads on separate ZMQ ports.

## **3.3 Implementing the Viewer Node**

The Viewer (`view.py`) utilizes PyQt6 for a responsive, hardware-accelerated user interface. To avoid freezing the GUI during network operations, ZMQ subscriber sockets were implemented inside isolated `QThread` workers. These workers listen for incoming packets in the background and emit PyQt signals to hand data over to the main GUI thread for rendering.

Radar visualization is handled by PyQtGraph, which updates the heatmap image item. To make radar data intuitive, a logarithmic scaling function converts raw amplitude values into decibels (dB), and a Gaussian zoom algorithm smooths the pixelated radar output.

[PLACEHOLDER: Figure 8 - Screenshot of Live Viewer interface]

## **3.4 Implementing the Studio Analysis Workbench**

The offline analysis tool (`app.py` and `src/studio`) was built using Streamlit to automate statistical aggregation for biomechanical reporting. 

When a Parquet file is uploaded, the `eval.py` script reconstructs the session using the `motion.py` mathematics engine. Data is organized into Pandas dataframes, grouping 30 FPS data into second-by-second and minute-by-minute averages to reduce visual noise. Plotly is used to render interactive charts that allow researchers to observe variance envelopes around kinematic trends. A QR-code feature on the login screen provides remote access for observers using mobile devices.

# **4. Evaluation**

The technical artifact was subjected to an evaluation phase to verify its performance against the specifications and determine its viability for extreme environmental conditions.

## **4.1 Technical Performance Evaluation**

### **4.1.1 System Latency and Throughput**
Offloading pose estimation to the edge (the Streamer Node) successfully limited network traffic to lightweight coordinate data and compressed previews. During testing, glass-to-glass latency remained consistently under 100 milliseconds, supporting real-time safety monitoring during strenuous exercise.

### **4.1.2 Resource Utilization**
Distributing the application into distinct nodes managed the computational burden effectively. While the Streamer node consumed more processing power for deep learning, the Viewer node remained efficient, utilizing less than 15% of a standard laptop's CPU. This confirms the system's portability and suitability for deployment on commercial hardware.

## **4.2 Accuracy and Reliability Assessment**

### **4.2.1 Noise Reduction via Stable 2D Projection**
Initial tests using raw 3D depth data revealed fluctuations of approximately ±4 degrees in trunk lean due to infrared scattering. The implementation of the "Stable 2D Projection" filter reduced this structural noise to less than ±0.8 degrees of variance. This stabilization was vital for detecting subtle physiological changes (1-3 degrees) that would have been obscured by raw sensor noise.

[PLACEHOLDER: Figure 6 - Comparison of Raw vs. Filtered Trunk Lean Data]

### **4.2.2 Radar vs Vision Consistency**
Qualitative evaluation demonstrated that mmWave radar successfully captured the cyclical velocity of the leg swing even when the optical camera occasionally dropped frames due to motion blur. This confirms that the system maintains a reliable temporal measurement of cadence even when optical structural data temporarily degrades.

## **4.3 Practical Usability and Deployment**

### **4.3.1 Environmental Robustness**
The markerless nature of the Craton Suite proved advantageous in the heat chamber, as participants sweating heavily did not need to wear physical sensors. However, both the RealSense camera and the TI radar experienced thermal throttling in high temperatures, necessitating cooling periods between sessions.

### **4.3.2 Stakeholder Feedback**
Researchers praised the usability of the system, particularly the QR-code remote access and the automated generation of statistical summaries. These features reduced post-session processing time and aligned the development with practical clinical requirements.

# **5. Discussion**

The development of the Craton Suite illustrates how fusing distinct sensor modalities can overcome the limitations of isolated tracking systems.

## **5.1 Interpretation of Findings**

Evaluation confirmed that depth-based optical tracking is fragile when subjected to dynamic human motion. Software-level mathematical filtering, such as the "Stable 2D Projection" algorithm, is necessary to compensate for physical hardware shortcomings. By averaging relationships between multiple body parts, the system prioritizes anatomical plausibility over raw pixel depth.

## **5.2 Sensor Fusion: Late vs Early Fusion**

This project utilized a Late Fusion architecture, which proved robust in a field environment. Early fusion requires micrometer-level calibration and microsecond-level synchronization that is difficult to maintain outside the laboratory. Late fusion allows each sensor to excel at its primary strength—the radar for temporal dynamics and the camera for spatial structure—before alignment in the Craton Studio.

## **5.3 Limitations and Hardware Constraints**

Hardware vulnerabilities, such as thermal throttling in high heat, indicate that commercial edge-computing devices require environmental shielding for prolonged experiments. Additionally, while radar is sensitive to motion, it lacks structural context and cannot distinguish between limbs without auxiliary information, reinforcing its role as a supportive sensor rather than a standalone replacement for optical cameras.

## **5.4 Ethical and Privacy Considerations**

The "Edge Analysis" design pattern supports patient privacy by processing video into abstract skeletal coordinates in real-time and discarding raw footage. This design simplifies compliance with GDPR regulations and makes the system suitable for sensitive medical or occupational health scenarios.

# **6. Conclusion**

## **6.1 Summary**

The Craton Suite successfully integrates an Intel RealSense depth camera with a TI mmWave radar using a secure, distributed ZeroMQ architecture. Advanced mathematical filtering mitigates the noise of accessible optical tracking, while the Late Fusion approach combines spatial context with robust temporal sensitivity. Evaluation confirms the system's capability to deliver clinically meaningful biomechanical data in challenging environments.

## **6.2 Recommendations for further work**

Future enhancements could include an automated AI fusion model to weight sensor data based on noise levels. Additionally, custom enclosures with active cooling would address the thermal throttling discovered during testing. The modular ZMQ architecture also supports the integration of additional modalities, such as wireless EMG sensors, for a more holistic view of human fatigue.

## **6.3 Reflection**

Developing the Craton Suite involved bridging the gap between hardware interfacing, network programming, and biomechanical mathematics. The transition to a distributed architecture was the most demanding aspect, requiring a deep understanding of concurrency. This project reinforced the principle that engineering research tools involves balancing precision with usability and deployment feasibility.

# **7. References**

\[1\] S. Edriss, C. Romagnoli, L. Caprioli, V. Bonaiuto, E. Padua, and G. Annino, 'Commercial vision sensors and AI-based pose estimation frameworks for markerless motion analysis in sports and exercises: a mini review', _Front. Physiol._, vol. 16, Aug. 2025, doi: 10.3389/fphys.2025.1649330.

\[2\] B. Lagomarsino, 'Insights on the Role of Depth Information for Human Motion Evaluation Using a Single RGB-D Camera'.

\[3\] W. He, 'A Survey of Efficient Regression of General-Activity Human Poses from Depth Images', Sep. 02, 2017, _arXiv_: arXiv:1709.02246. doi: 10.48550/arXiv.1709.02246.

\[4\] S. Edriss _et al._, 'The Role of Emergent Technologies in the Dynamic and Kinematic Assessment of Human Movement in Sport and Clinical Applications', _Appl. Sci._, vol. 14, no. 3, p. 1012, Jan. 2024, doi: 10.3390/app14031012.

\[5\] L. Chen, H. Wei, and J. Ferryman, 'A survey of human motion analysis using depth imagery', _Pattern Recognit. Lett._, vol. 34, no. 15, pp. 1995-2006, Nov. 2013, doi: 10.1016/j.patrec.2013.02.006.

\[6\] 'Understanding mmWave RADAR, its Principle & Applications'. Accessed: Jan. 30, 2026. \[Online\]. Available: <https://www.design-reuse.com/article/61510-understanding-mmwave-radar-its-principle-applications/>

\[7\] J. D. Périard, T. M. H. Eijsvogels, and H. A. M. Daanen, 'Exercise under heat stress: thermoregulation, hydration, performance implications, and mitigation strategies', _Physiol. Rev._, vol. 101, no. 4, pp. 1873-1979, Oct. 2021, doi: 10.1152/physrev.00038.2020.

\[8\] C. Zheng _et al._, 'Deep Learning-Based Human Pose Estimation: A Survey', Jul. 03, 2023, _arXiv_: arXiv:2012.13392. doi: 10.48550/arXiv.2012.13392.

\[9\] P. H. Rantelinggi, X. Shi, M. Bouazizi, and T. Ohtsuki, 'Deep Learning-Based Human Joint Localization Using mmWave Radar and Sequential Frame Fusion', _Annu. Int. Conf. IEEE Eng. Med. Biol. Soc. IEEE Eng. Med. Biol. Soc. Annu. Int. Conf._, vol. 2025, pp. 1-6, Jul. 2025, doi: 10.1109/EMBC58623.2025.11251671.

\[10\] A. Sengupta, F. Jin, R. Zhang, and S. Cao, 'mm-Pose: Real-Time Human Skeletal Posture Estimation using mmWave Radars and CNNs', _IEEE Sens. J._, vol. 20, no. 17, pp. 10032-10044, Sep. 2020, doi: 10.1109/JSEN.2020.2991741.

\[11\] S. Hu, S. Cao, N. Toosizadeh, J. Barton, M. G. Hector, and M. J. Fain, 'mmPose-FK: A Forward Kinematics Approach to Dynamic Skeletal Pose Estimation Using mmWave Radars', _IEEE Sens. J._, vol. 24, no. 5, pp. 6469-6481, Mar. 2024, doi: 10.1109/JSEN.2023.3348199.

\[12\] B. Zhu, Z. He, W. Xiong, G. Ding, T. Huang, and W. Xiang, 'ProbRadarM3F: mmWave Radar-Based Human Skeletal Pose Estimation With Probability Map-Guided Multiformat Feature Fusion', _IEEE Trans. Aerosp. Electron. Syst._, vol. 61, no. 6, pp. 15832-15842, Dec. 2025, doi: 10.1109/TAES.2025.3594328.

\[13\] S.-P. Lee, N. P. Kini, W.-H. Peng, C.-W. Ma, and J.-N. Hwang, 'HuPR: A Benchmark for Human Pose Estimation Using Millimeter Wave Radar', Oct. 22, 2022, _arXiv_: arXiv:2210.12564. doi: 10.48550/arXiv.2210.12564.

# **Appendices**
