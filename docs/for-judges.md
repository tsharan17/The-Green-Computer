# For judges: how to try The Green Computer in two minutes

No login is needed. Open the demo URL, click **Robot that spots objects**, then press **Analyse my setup**.

## What you will see

1. **Verdict.** The robot example (YOLOv8s on a Jetson Orin NX at 30 frames per second, 40 °C, under 55 W, at least 90% accuracy) fails today: the chip overheats and slows itself down to 70% of its speed. A changed setup meets every requirement and uses about 59% less power.
2. **The cheapest fix.** Ranked by how little engineering work each takes, not just by energy.
3. **Recommendations at four levels:** change the AI model (FP16/INT8, pruning, smaller input, a lighter model), change how you run it (batching, power mode, clock cap), choose better hardware (another board, better cooling), and redesign the chip or board (what-if ideas such as faster memory or power gating, with the modelled effect of each). Every item says what it gains, why, what it costs, how sure we are and how to check it.
4. **Export.** A shareable report and a recipe (scripts to convert the model, build a TensorRT engine, set the Jetson power mode, measure on the board, plus design notes for hardware engineers).
5. **Real measurements.** Predicted versus measured, with calibration that is applied only if it predicts held-out measurements better.

Try the other examples, especially **Too much for the board**: it fails, says exactly why, and shows what would work instead without ever loosening your requirements.

## How it uses Nebius and NVIDIA

- **NVIDIA Nemotron on Nebius Token Factory** powers the Green Agent (the **Describe** page, right-hand side). It plans, calls the engine through tools and explains; it never computes a number. A guardrail rejects any figure in its reply that is not in a tool result, and it cannot change your requirements.
- **Nebius Serverless Jobs on NVIDIA GPUs** run real benchmarks that feed calibration. Launching them is switched off in the public demo because it spends credits.
- **Tavily** finds datasheets for hardware that is not in the library; Nemotron extracts the values; a person confirms them.

## Please read: what is and is not verified

- The performance, power and heat numbers are **predictions** from a physics model with stated assumptions and best-case to worst-case ranges. The only real measurements so far are ResNet-50 and MobileNetV2 latency on the developer's CPU. **No Jetson, GPU or power measurement exists yet**, so Jetson results are analytical.
- The Green Agent, GPU job launcher and datasheet import were built from the Nebius and Tavily documentation and tested against fakes. **They had not been run against the live services when this was written.** If the agent is not configured on the demo you will see a clear message; everything else works without it.
- Generated recipes are syntax-checked, never run on a device.
- The chip-design what-ifs come from a simple model with no on-chip memory detail: they are directional.

## Run your own copy

See the [README](../README.md). `scripts/acceptance.py <url>` checks a running copy end to end as a judge would.
