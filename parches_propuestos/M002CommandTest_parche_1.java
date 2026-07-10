--- a/source/src/test/java/com/sixgroup/refit/billing/watcher/inbound/command/type/M002CommandTest.java
+++ b/source/src/test/java/com/sixgroup/refit/billing/watcher/inbound/command/type/M002CommandTest.java
@@ -40,12 +40,11 @@
 
         // then
         assertNotNull(response, "La respuesta no debe ser nula");
-        Thread.sleep(50);
         verify(params, times(1)).getMovFecha();
         verify(params, times(1)).getCommandId();
         verify(reportsExecutionService, times(1)).start(eq("M002"), eq(1), eq("2025-08-28"));
         verifyNoMoreInteractions(reportsExecutionService);
     }
 
     @Test
-    void getType_returnsM001() {
+    void getType_returnsM002() {
         RftCommandName type = command.getType();
         assertEquals(BillingCommandName.M002, type);
     }