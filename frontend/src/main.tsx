import React from "react";
import ReactDOM from "react-dom/client";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-sans/700.css";
import App from "./App";
import { setUpInstall } from "./components/Install";
import { keepScrollersFocusable } from "./lib/scrollers";
import "./styles.css";
import "./friendly.css";
import "./theme.css";
import "./workflow.css";
import "./pro.css";
import "./public.css";

setUpInstall();
keepScrollersFocusable();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
