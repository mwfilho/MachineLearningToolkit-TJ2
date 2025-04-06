# PJE Document Merger API Documentation

## Overview

This API provides functionality to interact with the PJE (Processo Judicial Eletrônico) system, allowing you to retrieve process information, download documents, and merge multiple documents into a single PDF file. The implementation leverages the National Interoperability Model (MNI) to communicate with judicial systems.

## Authentication

All API endpoints require MNI authentication. You can provide authentication credentials in one of two ways:

1. **Request Headers**:
   ```
   X-MNI-CPF: [Consultant ID]
   X-MNI-SENHA: [Consultant Password]
   ```

2. **Environment Variables**:
   - `MNI_ID_CONSULTANTE`: Consultant ID (CPF)
   - `MNI_SENHA_CONSULTANTE`: Consultant Password

## API Endpoints

### 1. Get Process Information

**Endpoint**: `GET /api/v1/processo/<num_processo>`

**Description**: Retrieves complete information about a judicial process, including a list of all available documents.

**Response**: JSON object containing process details, including:
- Basic process information
- Involved parties
- Subjects
- Timeline of events
- List of available documents

**Example**:
```
GET /api/v1/processo/0123456-78.2020.5.03.0001
```

### 2. Download Document

**Endpoint**: `GET /api/v1/processo/<num_processo>/documento/<num_documento>`

**Description**: Downloads a specific document from the process.

**Response**: Binary file (PDF, HTML, etc.) with appropriate MIME type.

**Example**:
```
GET /api/v1/processo/0123456-78.2020.5.03.0001/documento/12345
```

### 3. Get Process Cover Information

**Endpoint**: `GET /api/v1/processo/<num_processo>/capa`

**Description**: Returns only the cover information of the process (without documents), for improved performance when the full document list is not needed.

**Response**: JSON object containing basic process information.

**Example**:
```
GET /api/v1/processo/0123456-78.2020.5.03.0001/capa
```

### 4. Get Initial Petition

**Endpoint**: `GET /api/v1/processo/<num_processo>/peticao-inicial`

**Description**: Retrieves the initial petition and its attachments.

**Response**: JSON object containing the initial petition and related documents.

**Example**:
```
GET /api/v1/processo/0123456-78.2020.5.03.0001/peticao-inicial
```

### 5. Download Complete Process PDF

**Endpoint**: `GET /api/v1/processo/<num_processo>/pdf`

**Description**: Downloads all documents from the process merged into a single PDF file. This is the main feature of the API, allowing you to retrieve a consolidated view of all process documents.

**Processing Details**:
- Fetches all documents from the judicial process
- Converts HTML documents to PDF format
- Merges all PDFs into a single file
- Includes linked/attached documents

**Response**: Binary PDF file containing all process documents.

**Example**:
```
GET /api/v1/processo/0123456-78.2020.5.03.0001/pdf
```

## Error Handling

All API endpoints follow a consistent error response format:

```json
{
  "erro": "Error type or code",
  "mensagem": "Human-readable error message"
}
```

Common error scenarios:
- Authentication errors (401)
- Invalid process number format (400)
- Process not found (404)
- Document conversion failures (500)
- General server errors (500)

## Process Number Format

The API accepts process numbers in CNJ (Conselho Nacional de Justiça) format:
```
NNNNNNN-NN.NNNN.N.NN.NNNN
```

The API will attempt to format non-standard inputs to the CNJ format when possible.

## Technical Notes

### HTML to PDF Conversion

For HTML documents, the system uses the `wkhtmltopdf` tool to convert content to PDF before merging. This ensures that all documents in the final merged PDF maintain proper formatting.

### Handling Linked Documents

The API recursively processes linked documents (attachments) to ensure that all relevant content is included in the final merged PDF.

### Performance Considerations

- Process fetching with documents is slower than fetching just the cover information
- HTML to PDF conversion adds processing time
- For processes with many documents, the merge operation may take longer to complete