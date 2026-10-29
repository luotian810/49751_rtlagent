`timescale 1ns/1ps
module tb;
 reg completed=0;
 reg tick_i=0,arst_ni=1,clear_i=0,advance_i=0;
 wire [2:0] pd,pr;
 wire wd,wr;
 integer errors=0,samples=0,i,n=0;
 reg pulse=0;
 reg [31:0] rng=32'h739a62b1;
 TopModule dut(.tick_i(tick_i),.arst_ni(arst_ni),.clear_i(clear_i),.advance_i(advance_i),.position_o(pd),.wrap_o(wd));
 RefModule refm(.tick_i(tick_i),.arst_ni(arst_ni),.clear_i(clear_i),.advance_i(advance_i),.position_o(pr),.wrap_o(wr));
 always #5 tick_i=~tick_i;
 task check;
   begin
     if({pr,wr}!=={n[2:0],pulse}) $fatal(1,"ORACLE_ERROR mod7 reset_n=%b clear=%b advance=%b ref=%d/%b expected=%0d/%b",arst_ni,clear_i,advance_i,pr,wr,n,pulse);
     samples=samples+1;
     if({pd,wd}!=={n[2:0],pulse}) begin
       errors=errors+1;
       if(errors==1) $display("FIRST_MISMATCH step=%0d reset_n=%b clear=%b advance=%b got=%d/%b expected=%0d/%b",samples,arst_ni,clear_i,advance_i,pd,wd,n,pulse);
     end
   end
 endtask
 task step(input r,c,e);
   begin
     @(posedge tick_i);arst_ni=r;clear_i=c;advance_i=e;
     if(!r) begin n=0;pulse=0;end
     #1;check;
     @(negedge tick_i);
     if(!r || c) begin n=0;pulse=0;end
     else begin pulse=e && (n==6);if(e) n=(n+1)%7;end
     #1;check;
   end
 endtask
 initial begin
   #1;advance_i=0;clear_i=0;arst_ni=0;n=0;pulse=0;#1;check;
   #1;arst_ni=1;#1;check;
   for(i=0;i<15;i=i+1) step(1,0,1);
   step(1,0,0);step(1,1,1);step(1,0,1);
   for(i=0;i<400;i=i+1) begin
     rng=1664525*rng+1013904223;
     step(rng[31:27]!=0,rng[26:23]==0,rng[7]);
   end
   // Assert reset between clock edges after producing nonzero state.
   step(1,1,0);step(1,0,1);
   #1;advance_i=0;clear_i=0;arst_ni=0;n=0;pulse=0;#1;check;
   #1;arst_ni=1;#1;check;
   step(1,0,0);completed=1;$finish;
 end

  final begin
    if(completed) begin
      $display("Hint: Total mismatched samples is %0d out of %0d samples",errors,samples);
      $display("Mismatches: %0d in %0d samples",errors,samples);
    end else $display("TIMEOUT fixture incomplete");
  end
  initial begin #1000000; $fatal(1,"TIMEOUT fixture watchdog"); end
endmodule
