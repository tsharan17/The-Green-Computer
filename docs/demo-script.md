# Demo video script (target 2:40, hard limit 3:00)

Record the real app. No music, or royalty-free only. Do not show keys. Use a clean browser window at desktop width.

| Time | On screen | Say (roughly) |
|---|---|---|
| 0:00 | Start page | "Will your AI run on your hardware, and how do you make it greener? The Green Computer predicts that before you build anything, then tells you exactly what to change." |
| 0:15 | Click **Robot that spots objects**, show the three requirements | "A robot has to run an object detector at 30 frames a second, under 55 watts, in a warm room, without losing accuracy." |
| 0:25 | Press **Analyse my setup** | "One click. We search thousands of settings and solve power, heat and throttling together." |
| 0:35 | Verdict card | "Today it fails: the chip overheats and slows itself to 70% of its speed. A changed setup meets every requirement and uses about 59% less power." |
| 0:50 | Cheapest fix | "These are the cheapest fixes, ranked by engineering effort, not just energy. Requirements are never loosened." |
| 1:00 | Four recommendation levels | "Four levels: the AI model itself, how you run it, which hardware, and, for chip designers, what-if ideas such as power gating, each with its modelled effect. Every item says why, what it costs and how sure we are." |
| 1:30 | Click one card's **How to check it**; show a Rough estimate badge | "We are honest: anything we cannot know from a prediction is labelled, with the step that would prove it." |
| 1:45 | Describe page, Green Agent | "The Green Agent, powered by NVIDIA Nemotron on Nebius Token Factory, plans and explains. It cannot invent a number: a guardrail rejects any figure that did not come from the engine, and it cannot change your requirements." (Show a real agent turn only if the live key works.) |
| 2:05 | Real measurements page | "Real measurements flow back. Calibration is accepted only if it predicts held-out measurements better. Here is predicted versus measured on real runs." |
| 2:20 | Export page | "Finally, a shareable report and a recipe: scripts to convert the model, build the engine, set the power mode, and measure on the board." |
| 2:35 | Start page | "Predict. Optimise. Verify. Make every computation count." |

Before recording: run `scripts/acceptance.py <url>`; set the agent key if you will show the agent; delete the test project if you recorded earlier takes. If the live agent or Nebius jobs have not been verified, **do not show them as working**: say what is built and what is tested.
