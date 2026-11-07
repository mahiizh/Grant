import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import { enableMocking } from "./mocks/browser";

async function bootstrap() {
  await enableMocking();

  const rootElement = document.getElementById("root");
  if (rootElement) {
    ReactDOM.createRoot(rootElement).render(
      <React.StrictMode>
        <App />
      </React.StrictMode>
    );
  }
}

bootstrap();
