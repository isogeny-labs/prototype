/* Valgrind client requests. Needs valgrind's headers (package `valgrind`). */
#include <stddef.h>
#include <valgrind/memcheck.h>

/* Called by ctcrypto::ct::declassify under the `ctgrind` feature. */
void ctcrypto_declassify(unsigned char *p, size_t n) { VALGRIND_MAKE_MEM_DEFINED(p, n); }

/* Marks a secret: any branch or address computed from it is then reported. */
void ctcheck_poison(unsigned char *p, size_t n) { VALGRIND_MAKE_MEM_UNDEFINED(p, n); }

int ctcheck_on_valgrind(void) { return RUNNING_ON_VALGRIND; }
