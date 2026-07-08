# Ringkasan Penurunan HTML Setelah Cleaning

- Folder raw: `../data/actual_raw_html`
- Folder cleaned: `../data/cleaned_html_2`
- Total pasangan file dibandingkan: **47**

## Tabel Per File
| match_key | raw_filename | cleaned_filename | raw_lines | cleaned_lines | lines_removed | lines_decrease_percent | raw_chars | cleaned_chars | chars_removed | chars_decrease_percent |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| override | employee_1.html | customer_export_employee.html | 6132 | 88 | 6044 | 98.56 | 260511 | 2886 | 257625 | 98.89 |
| override | profile_1.html | customer_user_profile.html | 6116 | 102 | 6014 | 98.33 | 260750 | 4126 | 256624 | 98.42 |
| attlog | attlog.html | customer_export_attlog.html | 6229 | 141 | 6088 | 97.74 | 264652 | 5021 | 259631 | 98.1 |
| device_admin | device_admin.html | customer_office_device_admin.html | 6563 | 161 | 6402 | 97.55 | 277951 | 5897 | 272054 | 97.88 |
| attendance | attendance.html | customer_report_attendance.html | 8743 | 246 | 8497 | 97.19 | 405617 | 10077 | 395540 | 97.52 |
| no_scan | no_scan.html | customer_report_no_scan.html | 6375 | 186 | 6189 | 97.08 | 273348 | 7669 | 265679 | 97.19 |
| rekap_work_monitoring | rekap_work_monitoring.html | customer_report_rekap_work_monitoring.html | 6419 | 207 | 6212 | 96.78 | 275443 | 8764 | 266679 | 96.82 |
| overtime_request | overtime_request.html | customer_report_overtime_request.html | 6656 | 226 | 6430 | 96.6 | 287105 | 10235 | 276870 | 96.44 |
| leave_request | leave_request.html | customer_report_leave_request.html | 6843 | 245 | 6598 | 96.42 | 294044 | 10962 | 283082 | 96.27 |
| attendance_detail | attendance_detail.html | customer_report_attendance_detail.html | 5973 | 242 | 5731 | 95.95 | 255980 | 10109 | 245871 | 96.05 |
| emp_no_fingerprint | emp_no_fingerprint.html | customer_report_emp_no_fingerprint.html | 6533 | 269 | 6264 | 95.88 | 281373 | 12590 | 268783 | 95.53 |
| position_functional | position_functional.html | customer_organization_position_functional.html | 6441 | 278 | 6163 | 95.68 | 275207 | 13215 | 261992 | 95.2 |
| inbox | inbox.html | customer_inbox.html | 6839 | 304 | 6535 | 95.55 | 288694 | 15850 | 272844 | 94.51 |
| scan | scan.html | customer_report_scan.html | 6689 | 302 | 6387 | 95.49 | 293642 | 15428 | 278214 | 94.75 |
| device_no_admin | device_no_admin.html | customer_office_device_no_admin.html | 6390 | 295 | 6095 | 95.38 | 273480 | 13774 | 259706 | 94.96 |
| admin_multy_office | admin_multy_office.html | customer_employee_admin_multy_office.html | 6495 | 356 | 6139 | 94.52 | 282490 | 20716 | 261774 | 92.67 |
| leave_allowance | leave_allowance.html | customer_attendance_leave_allowance.html | 7414 | 495 | 6919 | 93.32 | 314532 | 21576 | 292956 | 93.14 |
| api_sdk | api_sdk.html | customer_device_api_sdk.html | 6600 | 450 | 6150 | 93.18 | 285677 | 23933 | 261744 | 91.62 |
| push_server | push_server.html | customer_device_push_server.html | 6599 | 450 | 6149 | 93.18 | 286370 | 24076 | 262294 | 91.59 |
| override | report_gps_tracking.html | customer_report_gps_tracking.html | 5230 | 378 | 4852 | 92.77 | 376330 | 14663 | 361667 | 96.1 |
| access_door | access_door.html | customer_office_access_door.html | 6582 | 487 | 6095 | 92.6 | 286707 | 26926 | 259781 | 90.61 |
| topup | topup.html | customer_topup.html | 6601 | 531 | 6070 | 91.96 | 282437 | 23710 | 258727 | 91.61 |
| resign | resign.html | customer_employee_resign.html | 7091 | 578 | 6513 | 91.85 | 306987 | 31608 | 275379 | 89.7 |
| schedule | schedule.html | customer_attendance_schedule.html | 7314 | 633 | 6681 | 91.35 | 313398 | 28719 | 284679 | 90.84 |
| confirm_attendance | confirm_attendance.html | customer_report_confirm_attendance.html | 7062 | 618 | 6444 | 91.25 | 603240 | 24118 | 579122 | 96.0 |
| no_calculate | no_calculate.html | customer_employee_no_calculate.html | 7075 | 640 | 6435 | 90.95 | 308246 | 34759 | 273487 | 88.72 |
| scan_gps | scan_gps.html | customer_report_scan_gps.html | 9554 | 925 | 8629 | 90.32 | 724681 | 38543 | 686138 | 94.68 |
| multy_office | multy_office.html | customer_employee_multy_office.html | 7325 | 716 | 6609 | 90.23 | 319996 | 38400 | 281596 | 88.0 |
| override | guide.html | customer_quick_guide.html | 7129 | 704 | 6425 | 90.12 | 324487 | 22876 | 301611 | 92.95 |
| spot | spot.html | customer_office_spot.html | 7225 | 734 | 6491 | 89.84 | 310351 | 37637 | 272714 | 87.87 |
| day_off | day_off.html | customer_attendance_day_off.html | 9427 | 1016 | 8411 | 89.22 | 509058 | 45475 | 463583 | 91.07 |
| employee_schedule | employee_schedule.html | customer_attendance_employee_schedule.html | 7616 | 918 | 6698 | 87.95 | 328842 | 41344 | 287498 | 87.43 |
| changelog | changelog.html | customer_changelog.html | 6909 | 857 | 6052 | 87.6 | 291576 | 34398 | 257178 | 88.2 |
| report | report.html | customer_setting_report.html | 7252 | 945 | 6307 | 86.97 | 309478 | 42052 | 267426 | 86.41 |
| leave | leave.html | customer_attendance_leave.html | 26494 | 3503 | 22991 | 86.78 | 1182125 | 177437 | 1004688 | 84.99 |
| organization | organization.html | customer_organization.html | 9772 | 1311 | 8461 | 86.58 | 712864 | 60868 | 651996 | 91.46 |
| dashboard | dashboard.html | customer_dashboard.html | 9395 | 1274 | 8121 | 86.44 | 431746 | 51343 | 380403 | 88.11 |
| invoice | invoice.html | customer_setting_invoice.html | 7398 | 1006 | 6392 | 86.4 | 327103 | 53786 | 273317 | 83.56 |
| overtime | overtime.html | customer_attendance_overtime.html | 8483 | 1416 | 7067 | 83.31 | 366676 | 75856 | 290820 | 79.31 |
| status | status.html | customer_attendance_status.html | 8504 | 1503 | 7001 | 82.33 | 370056 | 77887 | 292169 | 78.95 |
| device | device.html | customer_device.html | 8489 | 1558 | 6931 | 81.65 | 370689 | 77708 | 292981 | 79.04 |
| office | office.html | customer_office.html | 9263 | 1702 | 7561 | 81.63 | 709011 | 86819 | 622192 | 87.75 |
| billing_info | billing_info.html | customer_setting_billing_info.html | 7912 | 1852 | 6060 | 76.59 | 329284 | 70289 | 258995 | 78.65 |
| cart | cart.html | customer_cart.html | 20832 | 6020 | 14812 | 71.1 | 1138054 | 324150 | 813904 | 71.52 |
| app | app.html | customer_employee_app.html | 14031 | 4376 | 9655 | 68.81 | 599542 | 210210 | 389332 | 64.94 |
| employee | employee.html | customer_employee.html | 25042 | 8581 | 16461 | 65.73 | 1406121 | 471342 | 934779 | 66.48 |
| profile | profile.html | customer_setting_profile.html | 16037 | 6282 | 9755 | 60.83 | 711560 | 316077 | 395483 | 55.58 |

## Rata-Rata Penurunan
| avg_lines_removed | avg_lines_decrease_percent | avg_chars_removed | avg_chars_decrease_percent | total_files_compared |
| --- | --- | --- | --- | --- |
| 7467.79 | 89.31 | 359821.43 | 89.11 | 47.0 |
