`timescale 1ns/1ps
module tb;
 reg completed=0;
 reg clk_i=0,reset_ni=1,send_valid_i=0,recv_ready_i=0;
 reg [4:0] send_data_i=0;
 wire sd,sr,vd,vr;
 wire [4:0] dd,dr;
 integer errors=0,samples=0,i,n=0,head=0,tail=0;
 reg take,put,ready_expected,valid_expected;
 reg [4:0] data_expected;
 reg [4:0] queue[0:2047];
 reg [31:0] rng=32'h81c45a39;
 TopModule dut(.clk_i(clk_i),.reset_ni(reset_ni),.send_valid_i(send_valid_i),.send_data_i(send_data_i),.send_ready_o(sd),.recv_ready_i(recv_ready_i),.recv_valid_o(vd),.recv_data_o(dd));
 RefModule refm(.clk_i(clk_i),.reset_ni(reset_ni),.send_valid_i(send_valid_i),.send_data_i(send_data_i),.send_ready_o(sr),.recv_ready_i(recv_ready_i),.recv_valid_o(vr),.recv_data_o(dr));
 always #5 clk_i=~clk_i;
 task check;
   begin
     ready_expected=(n<2)||(recv_ready_i && n>0);
     valid_expected=(n>0);
     data_expected=(n==0)?5'b0:queue[head];
     if({sr,vr,dr}!=={ready_expected,valid_expected,data_expected}) $fatal(1,"ORACLE_ERROR fifo2 reset_n=%b send=%b take=%b in=%d ref=%b/%b/%d expected=%b/%b/%d",reset_ni,send_valid_i,recv_ready_i,send_data_i,sr,vr,dr,ready_expected,valid_expected,data_expected);
     samples=samples+1;
     if({sd,vd,dd}!=={ready_expected,valid_expected,data_expected}) begin
       errors=errors+1;
       if(errors==1) $display("FIRST_MISMATCH step=%0d reset_n=%b send_valid=%b recv_ready=%b in=%0d got=%b/%b/%0d expected=%b/%b/%0d",samples,reset_ni,send_valid_i,recv_ready_i,send_data_i,sd,vd,dd,ready_expected,valid_expected,data_expected);
     end
   end
 endtask
 task step(input r,s,t,input [4:0] d);
   begin
     @(negedge clk_i);reset_ni=r;send_valid_i=s;recv_ready_i=t;send_data_i=d;
     if(!r) begin n=0;head=0;tail=0;end
     #1;check;
     @(posedge clk_i);
     if(!r) begin n=0;head=0;tail=0;end
     else begin
       take=t && n>0;put=s && (n<2 || take);
       if(take) begin head=head+1;n=n-1;end
       if(put) begin queue[tail]=d;tail=tail+1;n=n+1;end
     end
     #1;check;
   end
 endtask
 initial begin
   #1;reset_ni=0;#1;check;#1;reset_ni=1;#1;check;
   step(1,0,1,0);step(1,1,1,7); // Empty cannot bypass a new word.
   step(1,1,0,11);step(1,1,0,31); // Full rejects a word with no take.
   step(1,1,1,19);step(1,1,1,23); // Full replacement in both pointer positions.
   step(1,0,1,0);step(1,0,1,0);step(1,0,1,0);
   for(i=0;i<600;i=i+1) begin
     rng=1664525*rng+1013904223;
     step(rng[31:27]!=0,rng[8],rng[7],rng[4:0]);
   end
   step(1,1,0,31);#1;send_valid_i=0;recv_ready_i=0;reset_ni=0;n=0;head=0;tail=0;#1;check;
   #1;reset_ni=1;#1;check;
   step(1,0,0,0);completed=1;$finish;
 end

  final begin
    if(completed) begin
      $display("Hint: Total mismatched samples is %0d out of %0d samples",errors,samples);
      $display("Mismatches: %0d in %0d samples",errors,samples);
    end else $display("TIMEOUT fixture incomplete");
  end
  initial begin #1000000; $fatal(1,"TIMEOUT fixture watchdog"); end
endmodule
