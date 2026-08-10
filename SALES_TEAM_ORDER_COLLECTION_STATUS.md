# 주문 현황 데이터 자동수집 검토 현황

- 작성일: 2026-08-07
- 공유 대상: 전략영업팀
- 검토 범위: 판매채널별 주문·배송 데이터 수집 자동화

## 1. 추진 목적

각 판매채널의 주문 및 배송 현황을 사람이 관리자 페이지에서 반복 확인하지 않고, 시스템에서 정기적으로 자동 수집하는 것을 목표로 한다.

현재 단계에서는 채널별 원본 데이터 수집까지만 담당한다. 여러 채널의 데이터 합산, 필터링 및 최종 판정 규칙은 별도 담당자가 수행할 예정이다.

## 2. 기본 추진 원칙

수집 방식은 다음 우선순위로 검토한다.

1. 판매채널이 제공하는 공식 API
2. 플랫폼이 승인한 제휴·셀링툴 API
3. API로 필요한 정보를 받을 수 없는 경우에만 관리자 페이지 크롤링

공식 API는 로그인 화면 변경이나 CAPTCHA의 영향을 받지 않고, 운영 안정성과 보안 측면에서도 크롤링보다 적합하다.

## 3. 네이버 스마트스토어 검증 결과

네이버 스마트스토어는 공식 네이버 커머스 API를 통해 주문 데이터를 수집할 수 있다.

실제 API 호출 검증을 완료했으며 다음 정보를 정상적으로 확인했다.

- 주문 및 상품주문 상태
- 상품명과 주문수량
- 결제일과 발송일
- 택배사와 송장번호
- 배송상태

판매자센터 로그인 세션이나 화면 크롤링 없이 API 인증정보만으로 자동수집할 수 있다.

**현재 판단: 공식 API 사용 확정**

## 4. 한촌몰·네이버페이 확인 결과

네이버페이 주문관리 API를 직접 사용하는 방안을 검토했으나, 한촌몰은 네이버페이에 독립몰이 아닌 **호스팅사 가맹점**으로 등록되어 있는 것으로 확인됐다.

네이버페이센터에서 API 연동 신청을 시도했을 때 다음 안내가 표시됐다.

> 호스팅사 사용 중인 가맹점의 API 연동 신청은 기술지원 문의 채널을 참고해 주세요.

따라서 한촌몰 계정에서는 네이버페이 주문관리 REST API용 애플리케이션 ID와 시크릿을 직접 발급받을 수 없다. 현재 보유한 네이버페이 가맹점 인증키와 버튼 인증키도 주문조회 REST API용 인증정보는 아니다.

## 5. 한촌몰 주문 수집 방향

한촌몰은 NHN커머스의 고도몰 기반으로 운영되고 있으므로, 일반 주문과 네이버페이 주문을 고도몰 주문 API에서 함께 수집하는 방향으로 진행한다.

```text
한촌몰 일반 주문 ─┐
                  ├─ 고도몰 주문 API → 주문 현황 자동수집
네이버페이 주문 ──┘
```

고도몰은 공식 주문조회 Open API를 제공한다. 다만 API 사용을 위해 NHN커머스 개발자센터에서 다음 인증정보를 별도로 발급받아야 한다.

- 제휴사키: 자체 개발 프로그램에 발급되는 인증키
- 사용자키: 해당 프로그램이 한촌몰 데이터에 접근하도록 승인하는 인증키

고도몰 쇼핑몰 관리자 화면의 `외부서비스 설정`은 구글 애널리틱스와 외부 스크립트 설정 메뉴이므로 Open API 키 발급 위치가 아니다. API 키는 [NHN커머스 개발자센터](https://aggregator.nhn-commerce.com/devcenter)에서 신청해야 한다.

## 6. 영업팀 협조 필요사항

한촌몰 주문 API 테스트를 위해 다음 사항의 확인 또는 협조가 필요하다.

- 한촌몰을 소유한 NHN커머스 통합회원 계정 확인
- NHN커머스 개발자센터에서 자체개발 Open API 개발자 등록
- 제휴사키 신청
- 한촌몰 도메인에 대한 사용자키 신청
- 한촌몰 대표 이메일로 발송되는 사용자 인증 메일 승인
- 발급 또는 권한에 제한이 있는 경우 NHN커머스 고객센터 문의

인증키 발급 후 다음 항목을 실제 API 응답에서 검증할 예정이다.

- 일반 주문과 네이버페이 주문의 포함 여부
- 고도몰 주문번호와 네이버페이 주문번호
- 상품명, 옵션 및 수량
- 결제수단과 주문상태
- 발송일, 택배사 및 송장번호
- 배송상태
- 취소·교환·반품 상태

## 7. 현재 진행 현황

| 채널 | 현재 상태 | 다음 조치 |
|---|---|---|
| 네이버 스마트스토어 | 공식 API 실제 호출 및 응답 필드 확인 완료 | 수집 모듈 운영화 |
| 한촌몰 | 고도몰 Open API 인증 및 실제 주문조회 검증 완료 | 수집 모듈 운영화 |
| 네이버페이 | 고도몰 주문 API에서 실제 네이버페이 주문 18건 확인 | 고도몰 주문 수집에 통합 |
| 쿠팡 WING | 공식 Open API 인증 및 실제 주문조회 검증 완료 | 수집 모듈 운영화 및 취소·반품 API 추가 검증 |
| CJ온스타일 | 직접개발 인증정보·IP 등록 완료, 방화벽 승인 대기 | 승인 후 배송 통합 조회 API 재호출 |
| 롯데ON | 인증 및 주문·배송 조회 API 호출 검증 완료 | 주문 발생 시 실제 응답 필드 추가 확인 |
| 지마켓·옥션 | ESM Trading API 제공 확인, 자체개발용 키는 현재 미확인 | ESM API 사용 승인 및 Secret Key 발급 요청 |
| 11번가 | 기존 API KEY·직접입력 IP 등록 및 결제완료 주문조회 호출 성공 | 주문 발생 시 실제 주문 필드 추가 확인 |
| SSG.COM | 운영 Open API 인증 및 배송지시 주문조회 성공, 최근 7일 1건 확인 | 운영 수집 모듈 구현 및 완료·클레임 API 범위 확장 |
| 알리익스프레스 | 공식 주문·주문상세·배송 API 제공 확인, 한국 판매자 계정의 개발자 등록 단계에서 `海外版禁止写入` 발생 | Open Platform 기술지원 메일 발송 완료, Self-developed Developer·화이트리스트 승인 대기 |
| 토스쇼핑 | Direct API 키·IP 등록 및 실제 주문조회 성공, 최근 7일 1건(`DELIVERED`) 확인 | 커서 페이지네이션·토큰 자동갱신 수집 모듈 구현 |
| 기타 판매채널 | API 제공 여부 1차 조사 완료 | 채널별 인증정보 발급 및 호출 검증 |

## 8. 결론

- 네이버 스마트스토어는 공식 API로 자동수집할 수 있으며 실제 호출까지 검증했다.
- 한촌몰 일반 주문, 네이버페이 주문과 페이코 주문은 고도몰 주문 API에서 함께 수집할 수 있음이 실제 응답으로 확인됐다.
- 고도몰 제휴사키와 사용자키 인증 및 주문조회 API 연결이 정상 작동한다.
- 이후 쿠팡 WING부터 판매채널별 실제 API 호출 검증을 순차적으로 진행한다.

## 9. 쿠팡 WING 실제 API 검증 결과

2026-08-07 쿠팡 WING Open API의 실제 호출 검증을 완료했다.

### 인증 및 연결

- WING에서 발급한 Vendor ID, Access Key 및 Secret Key 사용
- 호출 PC의 공인 IP를 WING Open API 설정에 등록
- HMAC-SHA256 요청 서명 인증 성공
- 주문조회 API `HTTP 200 / OK` 응답 확인
- 별도의 판매자센터 로그인 세션이나 브라우저 크롤링 불필요

### 최근 7일 상태별 조회 결과

개인정보 및 실제 주문값은 출력하지 않고 상태별 반환 건수와 응답 필드 구조만 확인했다.

| 쿠팡 상태 | 의미 | 검증 결과 |
|---|---|---|
| `ACCEPT` | 결제완료 | HTTP 200, 해당 기간 0건 |
| `INSTRUCT` | 상품준비중 | HTTP 200, 3건 반환 |
| `DEPARTURE` | 배송지시 | HTTP 200, 해당 기간 0건 |
| `DELIVERING` | 배송중 | HTTP 200, 1건 반환 |
| `FINAL_DELIVERY` | 배송완료 | HTTP 200, 첫 페이지 5건 및 다음 페이지 존재 |

### 확인된 주요 주문·배송 필드

- 주문 식별자: `orderId`, `shipmentBoxId`
- 주문·결제 일시: `orderedAt`, `paidAt`
- 주문상태: `status`
- 배송비 및 도서산간 비용
- 상품 ID, 옵션 ID, 판매자 상품코드
- 상품명, 옵션명 및 주문수량
- 판매가, 주문금액 및 할인금액
- 취소수량과 취소보류수량
- 예상·계획 배송일
- 택배사: `deliveryCompanyName`
- 송장번호: `invoiceNumber`
- 배송중 전환일: `inTrasitDateTime`
- 배송완료일: `deliveredDate`

### 판정

쿠팡 WING 주문·배송 현황은 공식 Open API로 수집할 수 있다. 로그인 자동화와 관리자 페이지 크롤링은 필요하지 않다. 운영 모듈에서는 상태별 조회, 페이지네이션(`nextToken`), 재시도, 키 만료 관리를 구현해야 한다.

## 10. CJ온스타일 표준 API 검증 현황

기존 CJ온스타일 계정에는 사방넷 셀러툴 연동이 설정되어 있다. 기존 운영에 영향을 주지 않도록 사방넷 설정은 유지하고, 직접개발 연동을 별도로 추가했다.

### 완료 사항

- 직접개발용 개발서버 공인 IP 등록
- 협력업체코드 `vendorCode` 확인: 공식 규격인 6자리와 일치
- API 인증키 `authenticationKey` 확인: 공식 규격인 60자리와 일치
- 주문·배송 API 중 `배송 통합 조회` 공식 엔드포인트 확인
  - QA: `https://qa-ingress-api.cjoshopping.com/delivery/getDeliveryList`
  - 운영: `https://ingress-api.cjoshopping.com/delivery/getDeliveryList`
- 요청 방식: `POST`, JSON

### 현재 상태

QA와 운영 엔드포인트에 연결을 시도했으나 모두 방화벽 단계에서 `HTTP 403 Forbidden`이 반환됐다. CJ온스타일 공식 안내상 신규 IP는 인프라팀의 방화벽 허용에 영업일 기준 2~3일이 걸릴 수 있으므로, 현재는 승인 대기 상태로 판단한다.

방화벽 허용 후 동일 API를 다시 호출하여 주문·상품·수량·배송상태·택배사·송장번호와 취소·회수 관련 응답 필드를 검증할 예정이다.

## 11. 롯데ON Open API 검증 결과

기존 롯데ON 계정에도 사방넷 셀러툴 연동이 설정되어 있다. 기존 사방넷 설정과 등록 IP를 유지한 상태에서 직접개발용 호출 IP와 별도 인증키를 추가했다.

### 인증 및 연결

- 직접개발용 공인 IP 등록
- 별도 Open API 인증키 발급 및 프로젝트 환경변수 저장
- 신원 확인 API 호출 성공
- `HTTP 200`, `returnCode: 0000` 확인
- 인증키와 등록 IP 모두 정상 작동

### 주문·배송 API 호출 결과

다음 공식 API를 실제 호출했다.

- 출고/회수지시 주문정보 조회
  - `POST /v1/openapi/delivery/v1/SellerDeliveryOrdersSearch`
- 롯데ON 배송상태 조회
  - `POST /v1/openapi/delivery/v1/SellerDeliveryProgressStateSearch`

두 API 모두 `HTTP 200`, `returnCode: 0000`으로 정상 응답했다. 최근 7일 조회 결과 반환 주문은 0건이었다. 신규 출고지시는 기존 사방넷이 먼저 연동 완료했을 가능성이 있으며, 배송상태 조회에도 해당 기간의 대상 주문이 없었다.

### 판정

롯데ON은 공식 Open API 인증과 주문·배송 조회 권한이 실제로 확인됐다. 로그인 자동화나 관리자 페이지 크롤링은 필요하지 않다. 주문이 발생한 시점에 주문번호, 상품·수량, 배송단계, 택배사, 송장번호 및 클레임 필드의 실제 응답 구조를 추가 확인한다.

## 12. 지마켓·옥션 ESM Trading API 확인 결과

지마켓과 옥션은 ESM PLUS 계정과 ESM Trading API를 통해 통합 관리할 수 있다. 공식 API에는 주문조회, 주문상태조회, 배송, 클레임 및 정산 기능이 제공된다.

### 현재 계정 상태

- ESM PLUS 마스터 ID가 생성되어 있음
- 셀링툴 사용 상태가 활성화되어 있음
- 상품 관리 셀링툴: 사방넷
- 주문 관리 셀링툴: 아워박스
- 화면에서 자체개발용 API Key 또는 Secret Key는 확인되지 않음
- 기존 셀링툴은 유지 가능하며 상품·주문 영역별로 업체를 추가할 수 있음

기존 사방넷 또는 아워박스의 인증키는 해당 셀링툴 업체에 부여된 키이므로 사내 수집 프로그램에서 재사용할 수 없다. 또한 `업체 추가하기`는 등록된 셀링툴을 추가하는 기능이며 자체개발용 키를 즉시 생성하는 기능은 아니다.

### 직접 수집을 위한 조건

자체개발 방식으로 API를 호출하려면 ESM API 담당자에게 사용 범위, ESM 마스터 ID, 서비스 URL, 매출 규모 및 개발 기간을 제출하고 승인을 받아야 한다. 승인 후 발급받을 Secret Key와 다음 판매자 식별정보를 사용해 JWT를 생성한다.

- ESM 마스터 ID
- ESM Secret Key
- 지마켓 판매자 ID
- 옥션 판매자 ID
- 허용 서버 IP

주문 수집의 대표 엔드포인트는 `POST https://sa2.esmplus.com/shipping/v1/Order/RequestOrders`이며 요청의 `siteType` 값으로 옥션(`1`)과 지마켓(`2`)을 구분한다. 조회 전용 API만 사용하면 기존 셀링툴의 주문확인·발송 업무와 직접적인 상태 변경 충돌은 발생하지 않는다.

### 판정

지마켓·옥션은 크롤링 대신 공식 ESM Trading API를 사용하는 것이 적합하다. 다만 현재 자체개발용 키가 확인되지 않았으므로 API 사용 승인 및 Secret Key 발급 전에는 실제 주문조회 호출을 검증할 수 없다.

## 13. 11번가 Open API 검증 결과

11번가는 공식 Open API Center에서 주문, 배송 및 취소·교환·반품 API를 제공한다. 기존에 발급된 API KEY가 확인됐으며 기존 허용 IP를 유지한 상태에서 직접개발용 로컬 PC 공인 IP를 추가했다.

### 인증 및 연결

- 기존 11번가 API KEY 확인 및 프로젝트 환경변수 저장
- 셀링툴 업체를 지정하지 않는 IP 직접입력 방식 사용
- 기존 개발·운영 IP 설정 유지
- 로컬 개발자 PC 공인 IP 추가
- API KEY 재발급은 수행하지 않음

### 주문조회 호출 결과

결제완료 주문을 조회하는 다음 조회 전용 API를 최근 7일 범위로 실제 호출했다.

```text
GET https://api.11st.co.kr/rest/ordservices/complete/{startDate}/{endDate}
Header: openapikey
```

호출 결과 `HTTP 200`과 XML 루트 요소 `orders`를 확인했다. 해당 기간에 반환된 결제완료 주문은 0건이며 응답에는 `result`, `result_code`, `result_text` 결과 요소가 포함됐다. 조회 API만 호출했으며 발주확인, 발송처리 또는 주문상태 변경 API는 호출하지 않았다.

### 판정

11번가는 로그인 자동화나 관리자 화면 크롤링 없이 공식 Open API로 주문 데이터를 직접 수집할 수 있다. 현재 키와 IP 인증이 정상 작동한다. 실제 주문이 반환되는 시점에 주문번호, 상품명·옵션·수량, 결제일시, 수취·배송정보, 택배사·송장번호 및 주문상태 필드를 추가 확인한다.

2026년 6월 30일부터 Open API 인증키 유효기간 180일 정책이 적용되므로 운영 모듈에는 키 만료일 관리와 갱신 알림이 필요하다.

## 14. 토스쇼핑 Open API 검증 결과

본 검토 대상은 결제대행사인 토스페이먼츠가 아니라 판매채널인 **토스쇼핑**이다. 토스쇼핑 파트너스의 `내 연동키` 메뉴에서 기존 사방넷 연동과 별도로 Direct API 키를 발급하고 호출 PC 공인 IP를 등록했다.

### 인증 및 실제 호출

- Access Key와 Secret Key를 이용한 OAuth2 Client Credentials 인증 성공
- Access Token 발급 성공, 실제 `expires_in` 3,599초 확인
- 운영 주문조회 API 최근 7일 범위 호출 성공

```text
POST https://oauth2.cert.toss.im/token
GET  https://shopping-fep.toss.im/api/v3/shopping-fep/orders/v2
```

| 항목 | 결과 |
|---|---:|
| API 결과 | `SUCCESS` |
| 조회기간 | 2026-08-03 ~ 2026-08-10 |
| 반환 주문상품 | 1건 |
| 주문상품 상태 | `DELIVERED` 1건 |
| 다음 커서 | 없음 |

### 확인된 응답 범위

- 주문·주문상품 ID: `orderId`, `orderProductId`
- 상품·재고 ID와 관리코드
- 상품명, 옵션명, 수량
- 판매가, 정상가, 할인액, 토스쇼핑·토스페이 할인 및 포인트
- 주문·취소·구매확정 일시
- 주문상품 상태
- 택배사, 송장번호 및 발송기한
- 기본·제주·도서산간 배송비
- 주문자·수령자·배송지 정보

주문목록은 최대 31일 범위로 조회하며 `nextCursor` 기반 페이지네이션을 사용한다. 주문상품 고유키는 `orderProductId`다. 개인정보 필드는 운영 로그와 저장 샘플에서 마스킹한다.

### 판정

토스쇼핑은 공식 Open API를 통해 한촌몰의 주문상품·금액·배송 데이터를 직접 자동 수집할 수 있다. 토큰은 실제 유효시간을 기준으로 만료 전에 자동 갱신하고, 채널별 저장 테이블은 `stg.TossShoppingOrderItem`으로 구성한다.

## 15. 한촌몰 고도몰 Open API 검증 결과

NHN커머스 개발자센터에서 기존 승인된 한촌몰 사용자키를 확인하고 제휴사키와 함께 프로젝트 환경변수에 등록했다. 고도몰5 공식 주문조회 API를 최근 7일 범위로 실제 호출했다.

```text
POST https://openhub.godo.co.kr/godomall5/order/Order_Search.php
```

### 인증 및 호출 결과

- 제휴사키 `partner_key`와 쇼핑몰 사용자키 `key` 인증 성공
- `HTTP 200`, 고도몰 결과코드 `000` 확인
- 최근 7일 주문 노드 46건 반환
- 조회 전용 API만 호출했으며 주문상태 변경 API는 호출하지 않음

### 주문채널별 반환 결과

| 주문채널 코드 | 의미 | 반환 건수 |
|---|---|---:|
| `shop` | 한촌몰 일반 주문 | 22 |
| `naverpay` | 네이버페이 주문 | 18 |
| `payco` | 페이코 주문 | 6 |
| 합계 | 전체 | 46 |

### 확인된 주요 데이터 구조

- 주문번호, 주문일시 및 결제일시
- 주문상태와 주문채널
- 주문상품명과 주문상품 수
- 주문상품 상세 배열
- 주문·상품 금액, 할인, 쿠폰, 마일리지 및 배송비
- 주문자·수령자 및 배송지 정보
- 배송 정보와 주문상담·처리 정보
- 외부 주문번호 `apiOrderNo`

### 판정

한촌몰 일반 주문과 네이버페이·페이코 주문은 하나의 고도몰 공식 API에서 통합 수집할 수 있다. 네이버페이 주문관리 API를 별도로 호출하거나 관리자 페이지를 크롤링할 필요가 없다. 운영 모듈에서는 `orderChannelFl`로 채널을 구분하고, 주문번호 기반 중복 방지와 `lastOrder` 페이지네이션을 구현한다.

## 16. SSG.COM Open API 검증 결과

SSG.COM 판매자 계정에 직접개발용 운영·테스트 서버 접속 IP를 추가하고 발급된 업체 인증키를 프로젝트 환경변수에 등록했다. 기존 사방넷 및 기존 등록 IP는 삭제하지 않고 유지했다.

2026-08-10 운영 서버의 배송지시목록조회 API를 주문완료일 기준 최근 7일 범위로 호출했다.

```text
POST https://eapi.ssgadm.com/api/pd/1/listShppDirection.ssg
Header: Authorization, Accept: application/json
Body: requestShppDirection (perdType=02, 시작일, 종료일)
```

| 항목 | 검증 결과 |
|---|---|
| HTTP 응답 | 200 |
| SSG 결과 | `resultCode: 00`, `resultMessage: SUCCESS`, `resultDesc: 성공` |
| 최근 7일 반환 건수 | 1건 |
| 상세 배송상태 | `11` 배송지시 1건 |
| 인증 방식 | 업체 인증키 + 등록 IP |
| 로그인 세션 | 불필요 |

실제 응답에서 주문·배송 식별자, 주문상태, 주문접수·완료일시, 사이트번호, 상품·단품·협력업체 상품 ID, 상품명, 지시·취소·주문수량, 공급가·판매가·결제가·할인가, 배송상태·상세 진행상태 및 출고예정일 필드를 확인했다. 수취인·주소·전화번호도 응답에 포함되므로 운영 로그에는 원문 개인정보를 남기지 않는다.

**현재 판단: SSG.COM은 공식 Open API로 주문·배송 데이터를 직접 자동 수집할 수 있으며, 로그인 자동화나 관리자 화면 크롤링이 필요하지 않다.**

## 17. 알리익스프레스 Open API 검토 현황

알리익스프레스는 공식 Open Platform에서 주문목록, 주문상세 및 배송정보 API를 제공한다. 자사 판매자 계정 연동에는 App Key, App Secret, 판매자 OAuth Access Token 및 Refresh Token이 필요하다.

확인한 주요 API는 다음과 같다.

- `aliexpress.solution.order.get`: 주문목록 조회
- `aliexpress.solution.order.info.get`: 주문상세 조회
- `aliexpress.solution.order.delivery.info.get`: 배송정보 조회

한국 판매자 계정으로 Open Platform 개발자 등록을 진행했으나 개발자 정보 제출 단계에서 `海外版禁止写入` 오류가 발생했다. 이는 입력값 오류가 아니라 해외 버전 계정의 해당 화면 등록이 제한된 상태를 의미한다.

2026-08-10 AliExpress Open Platform 기술지원(`aeop-support@aliexpress.com`)에 다음 사항을 문의했다.

- 한국 판매자의 Self-developed Developer 등록 방법
- App Key 및 App Secret 발급 절차
- 주문·배송 API 권한 신청 방법
- 해외 판매자 API 화이트리스트 승인 필요 여부

**현재 판단: 공식 API는 존재하지만 한국 판매자 계정의 직접개발 권한과 화이트리스트 승인이 필요하므로, 기술지원 회신 및 실제 API 호출 전까지 수집 가능 확정 채널에는 포함하지 않는다.**

## 18. 참고 자료

- [네이버 커머스 API](https://apicenter.commerce.naver.com/docs/commerce-api/current)
- [네이버페이 주문형 가맹점 API 기술지원](https://github.com/npay-mall-order-api/merchant-order-api)
- [고도몰 Open API 인증키 발급 안내](https://devcenter-help.nhn-commerce.com/guide/preparation/openapi-guide/userkey)
- [고도몰 Open API 스펙](https://devcenter.nhn-commerce.com/godomall5/openapi/specDownload)
- [쿠팡 OpenAPI Key 발급](https://developers.coupangcorp.com/hc/ko/articles/20288952179993-OpenAPI-Key-%EB%B0%9C%EA%B8%89%EB%B0%9B%EA%B8%B0)
- [쿠팡 발주서 목록 조회](https://developers.coupangcorp.com/hc/ko/articles/360033792774-%EB%B0%9C%EC%A3%BC%EC%84%9C-%EB%AA%A9%EB%A1%9D-%EC%A1%B0%ED%9A%8C-%EB%B6%84%EB%8B%A8%EC%9C%84-%EC%A0%84%EC%B2%B4)
- [CJ온스타일 표준 API 안내](https://partners.cjonstyle.com/standardApi/apiGuide)
- [CJ온스타일 API Docs](https://partners.cjonstyle.com/standardApi/apiDocs)
- [롯데ON Open API 이용안내](https://api.lotteon.com/apiGuide)
- [롯데ON Open API 시작하기](https://api.lotteon.com/apiService/?apiNm=GetStarted)
- [롯데ON 출고·회수지시 조회](https://api.lotteon.com/apiService/?apiMjrVerCd=V1&apiMnrVerNm=1.0&apiNo=209&menuIdx=9)
- [롯데ON 배송상태 조회](https://api.lotteon.com/apiService/?apiMjrVerCd=V1&apiMnrVerNm=1.0&apiNo=140&menuIdx=9)
- [ESM Trading API 사용 가이드](https://etapi.gmarket.com/pages/API-%EA%B0%80%EC%9D%B4%EB%93%9C)
- [ESM 주문·배송 API](https://etapi.gmarket.com/category/%EC%A3%BC%EB%AC%B8%20%7C%20%EB%B0%B0%EC%86%A1%20API)
- [11번가 Open API Center](https://openapi.11st.co.kr/openapi/OpenApiFrontMain.tmall)
- [11번가 주문 API 소개](https://openapi.11st.co.kr/openapi/OpenApiServiceIntroduce.tmall?introduceType=ORDER)
- [토스쇼핑 API 소개](https://shopping-docs.toss.im/dev)
- [토스쇼핑 인증 토큰 발급](https://shopping-docs.toss.im/dev/api-1/token)
- [토스쇼핑 주문 API](https://shopping-docs.toss.im/dev/api-2/order)
- [SSG.COM Open API](https://eapi.ssgadm.com/info/main.ssg)
- [SSG.COM 배송지시목록조회 API](https://eapi.ssgadm.com/info/shpp/listShppDirection.ssg)
- [AliExpress Open Platform 주문목록 API](https://developer.alibaba.com/docs/api.htm?apiId=42270)
- [AliExpress 해외 판매자 연동 절차](https://developer.alibaba.com/docs/doc.htm?articleId=108013&docType=1&treeId=502)
