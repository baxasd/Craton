# Community & Code of Conduct

We are building a high-performance, distributed suite for kinematics and radar telemetry. To keep the project moving fast and the core system stable, we have a few strict ground rules for anyone participating, opening issues, or writing code.

## 🧪 Where We Want Your Help (Contributions Welcome!)
We actively encourage forks, experiments, and Pull Requests for **OST Studio** and the **metrics calculations**. 
* **Algorithms:** Got a better way to calculate joint angles, micro-Doppler signatures, or velocity? We want it.
* **UI/UX:** Improvements in UI and UX, Streamlit dashboards and other user-to-program features
* **Efficiency:** Found a faster way to parse `.parquet` files or optimize pandas dataframes? Please share.

## 🚧 The Hard Boundaries
1. **Do not touch the hardware layer:** PRs modifying `stream.py`, sensor drivers, or the ZMQ network architecture will be rejected unless explicitly agreed upon in an Issue first
2. **Review your AI-generated code:** Review and Test AI-generated code, as ai prone to hallucinations and making mistakes. 

## 🤝 General Conduct
* **Be professional:** We are here to build good software. Harassment, discriminatory language, or personal attacks are strictly prohibited.
* **Be specific:** When reporting bugs, provide the exact logs, OS, and hardware you are using. "It doesn't work" is not a bug report.
* **Respect the maintainers' time:** Keep PRs focused on a single feature or bug fix so they are easy to review and merge.