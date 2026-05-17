export interface RuntimeRequest {
    [key: string]: unknown;
}
export type RuntimeResponse<T> = {
    ok: true;
    data: T;
    canonical_revision: number | null;
    duration_ms: number;
} | {
    ok: false;
    code: string;
    message: string;
    duration_ms: number;
};
export declare function queryRuntime<T>(body: RuntimeRequest): Promise<RuntimeResponse<T>>;
export declare function decideRuntime<T>(body: RuntimeRequest): Promise<RuntimeResponse<T>>;
export declare function ingestRuntime<T>(body: RuntimeRequest): Promise<RuntimeResponse<T>>;
export declare function statusRuntime<T>(): Promise<RuntimeResponse<T>>;
export declare function graphQueryRuntime<T>(body: RuntimeRequest): Promise<RuntimeResponse<T>>;
export declare function insightsDeriveRuntime<T>(body: RuntimeRequest): Promise<RuntimeResponse<T>>;
export declare function briefingRuntime<T>(): Promise<RuntimeResponse<T>>;
//# sourceMappingURL=runtime-client.d.ts.map