const PREFECT_API_URL = process.env.PREFECT_API_URL;
const PREFECT_API_KEY = process.env.PREFECT_API_KEY;

interface FlowRunResponse {
  id: string;
  state: { type: string; name: string };
}

class PrefectClient {
  private apiUrl: string;
  private apiKey: string;

  constructor() {
    if (!PREFECT_API_URL || !PREFECT_API_KEY) {
      throw new Error(
        "PREFECT_API_URL and PREFECT_API_KEY must be set in environment variables",
      );
    }
    this.apiUrl = PREFECT_API_URL.replace(/\/+$/, "");
    this.apiKey = PREFECT_API_KEY;
  }

  private async getDeploymentId(
    flowName: string,
    deploymentName: string,
  ): Promise<string> {
    const url = `${this.apiUrl}/deployments/name/${flowName}/${deploymentName}`;
    const response = await fetch(url, {
      headers: { Authorization: `Bearer ${this.apiKey}` },
    });
    if (!response.ok) {
      const body = await response.text();
      throw new Error(
        `Prefect deployment lookup error (${response.status}): ${body}`,
      );
    }
    const data = (await response.json()) as { id: string };
    return data.id;
  }

  async createFlowRun(
    flowName: string,
    deploymentName: string,
    parameters?: Record<string, unknown>,
  ): Promise<FlowRunResponse> {
    const deploymentId = await this.getDeploymentId(flowName, deploymentName);
    const url = `${this.apiUrl}/deployments/${deploymentId}/create_flow_run`;

    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${this.apiKey}`,
      },
      body: JSON.stringify({ parameters: parameters ?? {} }),
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(
        `Prefect API error (${response.status}): ${body}`,
      );
    }

    return response.json() as Promise<FlowRunResponse>;
  }
}

export const prefect = new PrefectClient();
