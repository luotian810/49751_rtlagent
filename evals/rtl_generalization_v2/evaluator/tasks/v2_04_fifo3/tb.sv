`timescale 1ns/1ps
module tb;
  reg completed=0;
  reg clk=0,reset=1,push=0,pop=0;reg [7:0] din=0;
  wire [7:0] dd,dr;wire ed,fd,er,fr;wire [1:0] cd,cr;
  integer errors=0,samples=0,i,n=0,head=0,tail=0;
  reg [7:0] model_mem[0:2047];
  reg take,put;reg [31:0] rng=32'hc001d00d;
  TopModule dut(.*,.dout(dd),.empty(ed),.full(fd),.count(cd));
  RefModule refm(.*,.dout(dr),.empty(er),.full(fr),.count(cr));
  always #5 clk=~clk;
  task check;
    reg [7:0] expected;
    begin
      expected=(n==0)?0:model_mem[head];
      if({cr,er,fr,dr} !== {n[1:0],(n==0),(n==3),expected})
        $fatal(1,"ORACLE_ERROR FIFO");
      samples=samples+1;if({cd,ed,fd,dd} !== {cr,er,fr,dr}) errors=errors+1;
    end
  endtask
  task step(input bit r,p,s,input [7:0] d);
    begin
      @(negedge clk);reset=r;push=p;pop=s;din=d;#1;check;
      @(posedge clk);
      if(r) begin n=0;head=0;tail=0;end
      else begin
        take=s && n>0;put=p && (n<3||take);
        if(take) begin head=head+1;n=n-1;end
        if(put) begin model_mem[tail]=d;tail=tail+1;n=n+1;end
      end
      #1;check;
    end
  endtask
  initial begin
    @(posedge clk);#1;
    step(0,0,1,0);step(0,1,1,8'h10);
    step(0,1,0,8'h20);step(0,1,0,8'h30);
    step(0,1,0,8'hff);step(0,1,1,8'h40);
    step(0,0,1,0);step(0,0,1,0);step(0,0,1,0);step(0,0,1,0);
    // Wrap both pointers many times, with all simultaneous corner cases.
    for(i=0;i<768;i=i+1) begin
      rng=1664525*rng+1013904223;
      step(rng[30:26]==0,rng[24],rng[23],rng[7:0]);
    end
    step(1,1,1,8'hee);step(0,0,0,0);completed=1;$finish;
  end
  final begin
    // Only a complete stimulus sequence can produce a valid result.
    if(completed) begin
    $display("Hint: Total mismatched samples is %0d out of %0d samples", errors, samples);
    $display("Mismatches: %0d in %0d samples", errors, samples);
    end else $display("TIMEOUT fixture incomplete");
  end
  initial begin #1000000; $fatal(1,"TIMEOUT fixture watchdog"); end
endmodule
