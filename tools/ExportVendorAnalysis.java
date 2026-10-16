// Headless Ghidra export. Analyzes PE data; never launches the vendor program.
// @category K810
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.nio.charset.StandardCharsets;

public class ExportVendorAnalysis extends GhidraScript {
    public void run() throws Exception {
        String sha = currentProgram.getExecutableSHA256().toLowerCase();
        if (!java.util.Set.of(
                "ef79b5e0ad1786dd682bc8ed1dad4626627c0518639ec67a702088d6322b8e36",
                "955cd803aa7c624bca3d9fd7bedcf4558a8139e4c0f125709cd09f88adaadc19",
                "ffed57d054e941b4543fd00a6ff4d0a068d39823cc1ee742fa033c2a20824b07").contains(sha))
            throw new IllegalArgumentException("Unknown vendor executable");
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException("Output directory required");
        File output = new File(args[0]);
        if (!output.isDirectory()) throw new IOException("Output directory must exist");
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        int total = 0, app = 0, failures = 0;
        try (PrintWriter functions = new PrintWriter(new File(output, "functions.tsv"), StandardCharsets.UTF_8);
             PrintWriter calls = new PrintWriter(new File(output, "calls.tsv"), StandardCharsets.UTF_8);
             PrintWriter code = new PrintWriter(new File(output, "application.c"), StandardCharsets.UTF_8)) {
            functions.println("address\tname\tsize\tthunk");
            calls.println("caller\tcall_site\ttarget\ttype");
            for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
                monitor.checkCancelled();
                total++;
                functions.printf("%s\t%s\t%d\t%b%n", f.getEntryPoint(), f.getName(), f.getBody().getNumAddresses(), f.isThunk());
                long address = f.getEntryPoint().getOffset();
                if (address < 0x400000L || address >= 0x445000L || f.isThunk()) continue;
                app++;
                if (app % 25 == 0) {
                    functions.flush(); calls.flush(); code.flush();
                    println("Exported application functions=" + app);
                }
                for (Instruction instruction : currentProgram.getListing().getInstructions(f.getBody(), true)) {
                    for (Reference reference : instruction.getReferencesFrom()) {
                        if (reference.getReferenceType().isCall())
                            calls.printf("%s\t%s\t%s\t%s%n", f.getEntryPoint(), instruction.getAddress(), reference.getToAddress(), reference.getReferenceType());
                    }
                }
                DecompileResults result = decompiler.decompileFunction(f, 30, monitor);
                code.printf("\n/* %s %s */\n", f.getEntryPoint(), f.getName());
                if (result.decompileCompleted()) code.println(result.getDecompiledFunction().getC());
                else { failures++; code.println("/* FAILED: " + result.getErrorMessage() + " */"); }
            }
        } finally { decompiler.dispose(); }
        println("Functions=" + total + " application=" + app + " failures=" + failures);
    }
}
