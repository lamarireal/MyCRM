import { useEffect, useState } from "react";

type ServiceState = "checking" | "online" | "offline";

interface HealthResponse {
  status: "ok" | "unavailable";
  service: string;
  version: string;
}

const apiUrl = import.meta.env.VITE_API_URL ?? "";

export function App() {
  const [serviceState, setServiceState] = useState<ServiceState>("checking");
  const [serviceVersion, setServiceVersion] = useState<string>();

  useEffect(() => {
    const controller = new AbortController();

    async function checkApi() {
      try {
        const response = await fetch(`${apiUrl}/api/v1/health/live`, {
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`Health check failed: ${response.status}`);

        const health = (await response.json()) as HealthResponse;
        setServiceVersion(health.version);
        setServiceState("online");
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setServiceState("offline");
        }
      }
    }

    void checkApi();
    return () => controller.abort();
  }, []);

  return (
    <main className="shell">
      <section className="hero" aria-labelledby="page-title">
        <div className="brand-mark" aria-hidden="true">
          M
        </div>
        <p className="eyebrow">Персональная CRM</p>
        <h1 id="page-title">MyCRM</h1>
        <p className="lead">
          Рабочее пространство для отношений, сделок и решений с ИИ внутри бизнес-логики.
        </p>

        <div className={`service-status service-status--${serviceState}`} role="status">
          <span className="status-dot" aria-hidden="true" />
          <span>
            {serviceState === "checking" && "Проверяем API…"}
            {serviceState === "online" && `API работает · v${serviceVersion}`}
            {serviceState === "offline" && "API недоступен"}
          </span>
        </div>
      </section>

      <section className="foundation" aria-label="Фундамент проекта">
        <p>Этап 0</p>
        <h2>Фундамент готов к развитию</h2>
        <ul>
          <li>FastAPI и версионированный контракт</li>
          <li>PostgreSQL и управляемые миграции</li>
          <li>React и строгая типизация</li>
        </ul>
      </section>
    </main>
  );
}
