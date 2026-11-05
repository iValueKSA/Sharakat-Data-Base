# Master Population & Lifecycle Reconciliation

Read-only database snapshot: **10/19/2026 14:02:33**. Fixed acceptance snapshot: **10/19/2026 13:58:36**. No sync was initiated.

## Population rule

Current lifecycle and opportunity queries begin with opportunities.merged_into_id IS NULL; the review snapshot labels those current rows eligible. Geographic/location acceptance is a separate filter and is not the lifecycle denominator.

The lifecycle population is the current non-merged Master population: `opportunities.merged_into_id IS NULL`. The five merged rows remain in the database but are superseded rows, and are excluded from current opportunity, dashboard, and lifecycle queries. “Eligible” in this reconciliation means this non-merged Master set; geographic/location eligibility is a separate query filter.

## Exact population sets

### `ALL_MASTER_ROWS` (296)

1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 170, 171, 172, 173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196, 197, 198, 199, 200, 201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211, 212, 213, 214, 215, 216, 217, 218, 219, 220, 221, 222, 223, 224, 225, 226, 227, 228, 229, 230, 231, 232, 233, 234, 235, 236, 237, 238, 239, 240, 241, 242, 243, 244, 245, 246, 247, 248, 249, 250, 251, 252, 253, 254, 255, 256, 257, 258, 259, 260, 261, 262, 263, 264, 265, 266, 267, 268, 269, 270, 271, 272, 273, 274, 275, 276, 277, 308, 309, 310, 311, 312, 313, 314, 315, 316, 317, 318, 319, 320, 321, 322, 323, 324, 325, 326

### `NON_MERGED_MASTERS` (291)

1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130, 131, 132, 133, 134, 136, 137, 138, 139, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 170, 171, 172, 173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196, 197, 198, 199, 200, 201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211, 212, 213, 214, 215, 216, 217, 218, 219, 220, 221, 222, 223, 224, 225, 226, 227, 228, 230, 231, 232, 233, 234, 235, 236, 237, 238, 239, 240, 241, 242, 243, 244, 245, 246, 247, 248, 249, 250, 251, 252, 253, 254, 255, 256, 257, 258, 259, 260, 261, 262, 263, 264, 265, 266, 267, 268, 269, 270, 271, 272, 273, 274, 275, 276, 277, 308, 309, 310, 311, 312, 313, 314, 315, 316, 317, 318, 319, 320, 321, 322, 323, 324, 325, 326

### `MERGED_MASTERS` (5)

74, 75, 135, 140, 229

### `ELIGIBLE_MASTERS` (291)

1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130, 131, 132, 133, 134, 136, 137, 138, 139, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 170, 171, 172, 173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196, 197, 198, 199, 200, 201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211, 212, 213, 214, 215, 216, 217, 218, 219, 220, 221, 222, 223, 224, 225, 226, 227, 228, 230, 231, 232, 233, 234, 235, 236, 237, 238, 239, 240, 241, 242, 243, 244, 245, 246, 247, 248, 249, 250, 251, 252, 253, 254, 255, 256, 257, 258, 259, 260, 261, 262, 263, 264, 265, 266, 267, 268, 269, 270, 271, 272, 273, 274, 275, 276, 277, 308, 309, 310, 311, 312, 313, 314, 315, 316, 317, 318, 319, 320, 321, 322, 323, 324, 325, 326

### `NON_ELIGIBLE_MASTERS` (5)

74, 75, 135, 140, 229

### `NON_ELIGIBLE_NON_MERGED_MASTERS` (0)

—

Merged-to targets:

| Merged Master ID | Superseded by Master ID | Stored status |
|---:|---:|---|
| 74 | 195 | Announced |
| 75 | 193 | Announced |
| 135 | 192 | Announced |
| 140 | 164 | Announced |
| 229 | 228 | EXPIRED |

## Mutually exclusive current lifecycle sets

Each listed item is a current non-merged, eligible Master. The JSON companion contains per-ID merged state, eligibility, active/historical flags, and canonical lifecycle status.

| Bucket | Count | Exact Master IDs |
|---|---:|---|
| AVAILABLE | 103 | 1, 2, 3, 4, 5, 6, 7, 8, 9, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 170, 171, 172, 173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196, 197, 198, 199, 200, 201, 202, 203, 204, 208, 209, 210, 226, 236, 238, 241, 243, 245, 247, 249, 250, 252, 254, 256, 259, 261, 263, 264, 265, 266, 267, 268, 269, 270, 271, 272, 273, 274, 275, 276, 277 |
| PUBLISHED | 158 | 10, 11, 12, 13, 14, 16, 17, 18, 19, 20, 21, 22, 24, 27, 28, 29, 31, 32, 33, 34, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 70, 71, 72, 73, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 123, 124, 125, 126, 127, 128, 129, 130, 131, 132, 133, 134, 136, 137, 141, 142, 205, 206, 207, 227, 230, 231, 232, 233, 234, 235, 237, 239, 240, 242, 244, 246, 248, 251, 253, 255, 257, 258, 260, 262, 308, 309, 310, 311, 312, 313, 314, 315, 316, 317, 318, 319, 320, 321, 322, 323, 324, 325 |
| EXPIRED | 2 | 224, 228 |
| HISTORICAL | 14 | 15, 23, 25, 26, 30, 35, 69, 90, 91, 109, 122, 138, 139, 225 |
| UNKNOWN | 1 | 326 |
| UNSPECIFIED | 13 | 211, 212, 213, 214, 215, 216, 217, 218, 219, 220, 221, 222, 223 |
| CANCELLED | 0 | — |

### Per-Master lifecycle rows

#### AVAILABLE

| Master ID | Merged | Eligible | Active | Historical flag | Canonical lifecycle status |
|---:|---|---|---|---|---|
| 1 | False | True | True | False | متاحة |
| 2 | False | True | True | False | متاحة |
| 3 | False | True | True | False | متاحة |
| 4 | False | True | True | False | متاحة |
| 5 | False | True | True | False | متاحة |
| 6 | False | True | True | False | متاحة |
| 7 | False | True | True | False | متاحة |
| 8 | False | True | True | False | متاحة |
| 9 | False | True | True | False | متاحة |
| 143 | False | True | True | False | متاحة |
| 144 | False | True | True | False | متاحة |
| 145 | False | True | True | False | متاحة |
| 146 | False | True | True | False | متاحة |
| 147 | False | True | True | False | متاحة |
| 148 | False | True | True | False | متاحة |
| 149 | False | True | True | False | متاحة |
| 150 | False | True | True | False | متاحة |
| 151 | False | True | True | False | متاحة |
| 152 | False | True | True | False | متاحة |
| 153 | False | True | True | False | متاحة |
| 154 | False | True | True | False | متاحة |
| 155 | False | True | True | False | متاحة |
| 156 | False | True | True | False | متاحة |
| 157 | False | True | True | False | متاحة |
| 158 | False | True | True | False | متاحة |
| 159 | False | True | True | False | متاحة |
| 160 | False | True | True | False | متاحة |
| 161 | False | True | True | False | متاحة |
| 162 | False | True | True | False | متاحة |
| 163 | False | True | True | False | متاحة |
| 164 | False | True | True | False | متاحة |
| 165 | False | True | True | False | متاحة |
| 166 | False | True | True | False | متاحة |
| 167 | False | True | True | False | متاحة |
| 168 | False | True | True | False | متاحة |
| 169 | False | True | True | False | متاحة |
| 170 | False | True | True | False | متاحة |
| 171 | False | True | True | False | متاحة |
| 172 | False | True | True | False | متاحة |
| 173 | False | True | True | False | متاحة |
| 174 | False | True | True | False | متاحة |
| 175 | False | True | True | False | متاحة |
| 176 | False | True | True | False | متاحة |
| 177 | False | True | True | False | متاحة |
| 178 | False | True | True | False | متاحة |
| 179 | False | True | True | False | متاحة |
| 180 | False | True | True | False | متاحة |
| 181 | False | True | True | False | متاحة |
| 182 | False | True | True | False | متاحة |
| 183 | False | True | True | False | متاحة |
| 184 | False | True | True | False | متاحة |
| 185 | False | True | True | False | متاحة |
| 186 | False | True | True | False | متاحة |
| 187 | False | True | True | False | متاحة |
| 188 | False | True | True | False | متاحة |
| 189 | False | True | True | False | متاحة |
| 190 | False | True | True | False | متاحة |
| 191 | False | True | True | False | متاحة |
| 192 | False | True | True | False | متاحة |
| 193 | False | True | True | False | متاحة |
| 194 | False | True | True | False | متاحة |
| 195 | False | True | True | False | متاحة |
| 196 | False | True | True | False | متاحة |
| 197 | False | True | True | False | متاحة |
| 198 | False | True | True | False | متاحة |
| 199 | False | True | True | False | متاحة |
| 200 | False | True | True | False | متاحة |
| 201 | False | True | True | False | متاحة |
| 202 | False | True | True | False | متاحة |
| 203 | False | True | True | False | متاحة |
| 204 | False | True | True | False | متاحة |
| 208 | False | True | True | False | متاحة |
| 209 | False | True | True | False | متاحة |
| 210 | False | True | True | False | متاحة |
| 226 | False | True | True | False | متاحة |
| 236 | False | True | True | False | متاحة |
| 238 | False | True | True | False | متاحة |
| 241 | False | True | True | False | متاحة |
| 243 | False | True | True | False | متاحة |
| 245 | False | True | True | False | متاحة |
| 247 | False | True | True | False | متاحة |
| 249 | False | True | True | False | متاحة |
| 250 | False | True | True | False | متاحة |
| 252 | False | True | True | False | متاحة |
| 254 | False | True | True | False | متاحة |
| 256 | False | True | True | False | متاحة |
| 259 | False | True | True | False | متاحة |
| 261 | False | True | True | False | متاحة |
| 263 | False | True | True | False | متاحة |
| 264 | False | True | True | False | متاحة |
| 265 | False | True | True | False | متاحة |
| 266 | False | True | True | False | متاحة |
| 267 | False | True | True | False | متاحة |
| 268 | False | True | True | False | متاحة |
| 269 | False | True | True | False | متاحة |
| 270 | False | True | True | False | متاحة |
| 271 | False | True | True | False | متاحة |
| 272 | False | True | True | False | متاحة |
| 273 | False | True | True | False | متاحة |
| 274 | False | True | True | False | متاحة |
| 275 | False | True | True | False | متاحة |
| 276 | False | True | True | False | متاحة |
| 277 | False | True | True | False | متاحة |

#### PUBLISHED

| Master ID | Merged | Eligible | Active | Historical flag | Canonical lifecycle status |
|---:|---|---|---|---|---|
| 10 | False | True | True | False | منشورة |
| 11 | False | True | True | False | منشورة |
| 12 | False | True | True | False | منشورة |
| 13 | False | True | True | False | منشورة |
| 14 | False | True | True | False | منشورة |
| 16 | False | True | True | False | منشورة |
| 17 | False | True | True | False | منشورة |
| 18 | False | True | True | False | منشورة |
| 19 | False | True | True | False | منشورة |
| 20 | False | True | True | False | منشورة |
| 21 | False | True | True | False | منشورة |
| 22 | False | True | True | False | منشورة |
| 24 | False | True | True | False | منشورة |
| 27 | False | True | True | False | منشورة |
| 28 | False | True | True | False | منشورة |
| 29 | False | True | True | False | منشورة |
| 31 | False | True | True | False | منشورة |
| 32 | False | True | True | False | منشورة |
| 33 | False | True | True | False | منشورة |
| 34 | False | True | True | False | منشورة |
| 36 | False | True | True | False | منشورة |
| 37 | False | True | True | False | منشورة |
| 38 | False | True | True | False | منشورة |
| 39 | False | True | True | False | منشورة |
| 40 | False | True | True | False | منشورة |
| 41 | False | True | True | False | منشورة |
| 42 | False | True | True | False | منشورة |
| 43 | False | True | True | False | منشورة |
| 44 | False | True | True | False | منشورة |
| 45 | False | True | True | False | منشورة |
| 46 | False | True | True | False | منشورة |
| 47 | False | True | True | False | منشورة |
| 48 | False | True | True | False | منشورة |
| 49 | False | True | True | False | منشورة |
| 50 | False | True | True | False | منشورة |
| 51 | False | True | True | False | منشورة |
| 52 | False | True | True | False | منشورة |
| 53 | False | True | True | False | منشورة |
| 54 | False | True | True | False | منشورة |
| 55 | False | True | True | False | منشورة |
| 56 | False | True | True | False | منشورة |
| 57 | False | True | True | False | منشورة |
| 58 | False | True | True | False | منشورة |
| 59 | False | True | True | False | منشورة |
| 60 | False | True | True | False | منشورة |
| 61 | False | True | True | False | منشورة |
| 62 | False | True | True | False | منشورة |
| 63 | False | True | True | False | منشورة |
| 64 | False | True | True | False | منشورة |
| 65 | False | True | True | False | منشورة |
| 66 | False | True | True | False | منشورة |
| 67 | False | True | True | False | منشورة |
| 68 | False | True | True | False | منشورة |
| 70 | False | True | True | False | منشورة |
| 71 | False | True | True | False | منشورة |
| 72 | False | True | True | False | منشورة |
| 73 | False | True | True | False | منشورة |
| 76 | False | True | True | False | منشورة |
| 77 | False | True | True | False | منشورة |
| 78 | False | True | True | False | منشورة |
| 79 | False | True | True | False | منشورة |
| 80 | False | True | True | False | منشورة |
| 81 | False | True | True | False | منشورة |
| 82 | False | True | True | False | منشورة |
| 83 | False | True | True | False | منشورة |
| 84 | False | True | True | False | منشورة |
| 85 | False | True | True | False | منشورة |
| 86 | False | True | True | False | منشورة |
| 87 | False | True | True | False | منشورة |
| 88 | False | True | True | False | منشورة |
| 89 | False | True | True | False | منشورة |
| 92 | False | True | True | False | منشورة |
| 93 | False | True | True | False | منشورة |
| 94 | False | True | True | False | منشورة |
| 95 | False | True | True | False | منشورة |
| 96 | False | True | True | False | منشورة |
| 97 | False | True | True | False | منشورة |
| 98 | False | True | True | False | منشورة |
| 99 | False | True | True | False | منشورة |
| 100 | False | True | True | False | منشورة |
| 101 | False | True | True | False | منشورة |
| 102 | False | True | True | False | منشورة |
| 103 | False | True | True | False | منشورة |
| 104 | False | True | True | False | منشورة |
| 105 | False | True | True | False | منشورة |
| 106 | False | True | True | False | منشورة |
| 107 | False | True | True | False | منشورة |
| 108 | False | True | True | False | منشورة |
| 110 | False | True | True | False | منشورة |
| 111 | False | True | True | False | منشورة |
| 112 | False | True | True | False | منشورة |
| 113 | False | True | True | False | منشورة |
| 114 | False | True | True | False | منشورة |
| 115 | False | True | True | False | منشورة |
| 116 | False | True | True | False | منشورة |
| 117 | False | True | True | False | منشورة |
| 118 | False | True | True | False | منشورة |
| 119 | False | True | True | False | منشورة |
| 120 | False | True | True | False | منشورة |
| 121 | False | True | True | False | منشورة |
| 123 | False | True | True | False | منشورة |
| 124 | False | True | True | False | منشورة |
| 125 | False | True | True | False | منشورة |
| 126 | False | True | True | False | منشورة |
| 127 | False | True | True | False | منشورة |
| 128 | False | True | True | False | منشورة |
| 129 | False | True | True | False | منشورة |
| 130 | False | True | True | False | منشورة |
| 131 | False | True | True | False | منشورة |
| 132 | False | True | True | False | منشورة |
| 133 | False | True | True | False | منشورة |
| 134 | False | True | True | False | منشورة |
| 136 | False | True | True | False | منشورة |
| 137 | False | True | True | False | منشورة |
| 141 | False | True | True | False | منشورة |
| 142 | False | True | True | False | منشورة |
| 205 | False | True | True | False | منشورة |
| 206 | False | True | True | False | منشورة |
| 207 | False | True | True | False | منشورة |
| 227 | False | True | True | False | منشورة |
| 230 | False | True | True | False | منشورة |
| 231 | False | True | True | False | منشورة |
| 232 | False | True | True | False | منشورة |
| 233 | False | True | True | False | منشورة |
| 234 | False | True | True | False | منشورة |
| 235 | False | True | True | False | منشورة |
| 237 | False | True | True | False | منشورة |
| 239 | False | True | True | False | منشورة |
| 240 | False | True | True | False | منشورة |
| 242 | False | True | True | False | منشورة |
| 244 | False | True | True | False | منشورة |
| 246 | False | True | True | False | منشورة |
| 248 | False | True | True | False | منشورة |
| 251 | False | True | True | False | منشورة |
| 253 | False | True | True | False | منشورة |
| 255 | False | True | True | False | منشورة |
| 257 | False | True | True | False | منشورة |
| 258 | False | True | True | False | منشورة |
| 260 | False | True | True | False | منشورة |
| 262 | False | True | True | False | منشورة |
| 308 | False | True | True | False | منشورة |
| 309 | False | True | True | False | منشورة |
| 310 | False | True | True | False | منشورة |
| 311 | False | True | True | False | منشورة |
| 312 | False | True | True | False | منشورة |
| 313 | False | True | True | False | منشورة |
| 314 | False | True | True | False | منشورة |
| 315 | False | True | True | False | منشورة |
| 316 | False | True | True | False | منشورة |
| 317 | False | True | True | False | منشورة |
| 318 | False | True | True | False | منشورة |
| 319 | False | True | True | False | منشورة |
| 320 | False | True | True | False | منشورة |
| 321 | False | True | True | False | منشورة |
| 322 | False | True | True | False | منشورة |
| 323 | False | True | True | False | منشورة |
| 324 | False | True | True | False | منشورة |
| 325 | False | True | True | False | منشورة |

#### EXPIRED

| Master ID | Merged | Eligible | Active | Historical flag | Canonical lifecycle status |
|---:|---|---|---|---|---|
| 224 | False | True | False | True | منتهية |
| 228 | False | True | False | True | منتهية |

#### HISTORICAL

| Master ID | Merged | Eligible | Active | Historical flag | Canonical lifecycle status |
|---:|---|---|---|---|---|
| 15 | False | True | False | True | أزيلت من المصدر |
| 23 | False | True | False | True | أزيلت من المصدر |
| 25 | False | True | False | True | أزيلت من المصدر |
| 26 | False | True | False | True | أزيلت من المصدر |
| 30 | False | True | False | True | أزيلت من المصدر |
| 35 | False | True | False | True | أزيلت من المصدر |
| 69 | False | True | False | True | أزيلت من المصدر |
| 90 | False | True | False | True | أزيلت من المصدر |
| 91 | False | True | False | True | أزيلت من المصدر |
| 109 | False | True | False | True | أزيلت من المصدر |
| 122 | False | True | False | True | أزيلت من المصدر |
| 138 | False | True | False | True | أزيلت من المصدر |
| 139 | False | True | False | True | أزيلت من المصدر |
| 225 | False | True | False | True | أزيلت من المصدر |

#### UNKNOWN

| Master ID | Merged | Eligible | Active | Historical flag | Canonical lifecycle status |
|---:|---|---|---|---|---|
| 326 | False | True | False | False | حالة غير معروفة |

#### UNSPECIFIED

| Master ID | Merged | Eligible | Active | Historical flag | Canonical lifecycle status |
|---:|---|---|---|---|---|
| 211 | False | True | False | False | غير محددة |
| 212 | False | True | False | False | غير محددة |
| 213 | False | True | False | False | غير محددة |
| 214 | False | True | False | False | غير محددة |
| 215 | False | True | False | False | غير محددة |
| 216 | False | True | False | False | غير محددة |
| 217 | False | True | False | False | غير محددة |
| 218 | False | True | False | False | غير محددة |
| 219 | False | True | False | False | غير محددة |
| 220 | False | True | False | False | غير محددة |
| 221 | False | True | False | False | غير محددة |
| 222 | False | True | False | False | غير محددة |
| 223 | False | True | False | False | غير محددة |

#### CANCELLED

| Master ID | Merged | Eligible | Active | Historical flag | Canonical lifecycle status |
|---:|---|---|---|---|---|

## Reconciliation

```ini
TOTAL_MASTER_ROWS = 296
NON_MERGED_MASTERS = 291
MERGED_MASTERS = 5
ELIGIBLE_MASTERS = 291
NON_ELIGIBLE_NON_MERGED_MASTERS = 0
CURRENT_LIFECYCLE_MASTER_POPULATION = 291
STATUS_BUCKET_UNION_COUNT = 291
STATUS_BUCKET_SUM = 291
STATUS_BUCKET_OVERLAP_COUNT = 0
MASTERS_WITHOUT_STATUS_BUCKET = 0
STATUS_POPULATION_RECONCILIATION = PASSED
```

### Why the earlier displayed bucket sum was 293

The earlier figure added `HISTORICAL_MASTERS=16` as a broad historical KPI to the mutually exclusive `EXPIRED_MASTERS=2`. The historical predicate includes expired rows, so these expired IDs were counted a second time:

- Expired Master IDs: **224, 228**.
- Broad historical KPI Master IDs: **15, 23, 25, 26, 30, 35, 69, 90, 91, 109, 122, 138, 139, 224, 225, 228**.
- Exact overlap: the two expired IDs above. The historical KPI is 16 (2 expired + 14 removed from source), but the exclusive `HISTORICAL` partition bucket is only the 14 removed-from-source Masters; `تمت الترسية` contributes none.
- Therefore, 103 + 158 + 2 + 16 + 1 + 13 + 0 = 293. Replacing broad `HISTORICAL=16` with the exclusive bucket `HISTORICAL=14` yields exactly 291. The current seven partition buckets have 291 unique IDs, overlap 0, and no missing IDs.

## Observation and scheduled sync boundary

The recorded 10,514 observation snapshot is **after** both natural scheduled jobs. The migration state immediately before them was 10,501. Furas job 343 created 13 removal-confirmation observations (IDs 10502–10514); the subsequent Al-Ahsa job 344 added none. Current DB observation count and maximum ID remain 10,514.

```ini
OBSERVATIONS_AT_FIXED_SNAPSHOT = 10514
OBSERVATIONS_BEFORE_NATURAL_SCHEDULED_SYNCS = 10501
OBSERVATIONS_AFTER_NATURAL_SCHEDULED_SYNCS = 10514
OBSERVATION_DELTA_FROM_SCHEDULED_SYNCS = 13
```

## Integrity and scope

This reconciliation performed read-only database queries. No status semantics, deadline/removal logic, mappings, Master aggregation, filters, dashboard, exports, taxonomy, location logic, observations, or business data were changed. The existing pre/post acceptance report documents 296 Master identities and 2,898 source links preserved; this reconciliation itself made zero business-data writes and started no manual source sync.

Acceptance: **PASSED**. Standardization Engine remains **16** per the existing final review.