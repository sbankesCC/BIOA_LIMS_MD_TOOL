// Front-end entry point: loads the global styles and mounts the app with the browser router.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import "./styles/tokens.css";
import "./styles/base.css";

// Mount into the #root element of index.html
const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("The page has no #root element, so the app cannot start. Check index.html.");
}
createRoot(rootElement).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
