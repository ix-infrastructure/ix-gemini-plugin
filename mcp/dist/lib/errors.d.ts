export declare const ERROR_LOG_PATH: string;
export type ErrorCode = "IX_UPSTREAM_UNAVAILABLE" | "IX_NOT_FOUND" | "IX_VALIDATION_ERROR" | "IX_AUTH_REQUIRED" | "IX_FORBIDDEN" | "IX_STALE_INDEX" | "IX_CONFLICTING_CLAIMS" | "IX_RATE_LIMITED" | "TIMEOUT" | "PARSE_FAILURE" | "VALIDATION" | "UNKNOWN";
export declare class IxError extends Error {
    readonly code: ErrorCode;
    readonly cause?: unknown | undefined;
    constructor(code: ErrorCode, message: string, cause?: unknown | undefined);
}
export declare function captureError(err: IxError, context: string): void;
//# sourceMappingURL=errors.d.ts.map